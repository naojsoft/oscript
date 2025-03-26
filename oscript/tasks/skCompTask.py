#!/usr/bin/env python
#
# skCompTask.py -- support file for running compiled skeleton files
#
# E. Jeschke
#
import time

# requires naojsoft "g2cam" package
from g2base import Bunch, Task

from oscript.tasks import g2Task
from oscript.parse.sk_common import Closure


class skCompError(Exception):
    pass


def async(parentTask):
    """Annotation function used to indicate an asynchronous skeleton file
    block.
    """
    def skblock(fn_block):
        task = Task.FuncTask(fn_block, (), {})
        parentTask.add_asynctask(task)

    return skblock


class skCompTask(g2Task.g2Task):
    """Subclass which adds support for skeleton files compiled to python
    tasks.
    """

    def __init__(self, *args, **kwdargs):
        super(skCompTask, self).__init__(*args, **kwdargs)

        self._stack = []

    def execdd(self, subsys, cmdname, **params):
        self.check_state()

        cmd_str = "EXEC %s %s %s" % (subsys, cmdname.upper(),
                                     self.fmtParams(params))
        self.logger.info("EXECDD: %s" % (cmd_str))

        classInfo = self.getFactory(cmdname, subsys=subsys)

        task = classInfo.klass(**params)
        return self.run(task)

    def execab(self, cmdname, **params):
        self.check_state()

        actuals = {}
        actuals.update(params)
        # Check for presence of special OBE_ID and OBE_MODE parameters
        try:
            obe_id = actuals['obe_id']
        except KeyError:
            raise SkCompError("No parameter set: OBE_ID")
        try:
            obe_mode = actuals['obe_mode']
        except KeyError:
            raise SkCompError("No parameter set: OBE_MODE")

        # Evaluate OBE_ID and OBE_MODE
        assert isinstance(obe_id, str), \
               skCompError("OBE_ID does not evaluate to a string")
        assert isinstance(obe_mode, str), \
               skCompError("OBE_MODE does not evaluate to a string")

        # Remove these two from the actuals
        del actuals['obe_id']
        del actuals['obe_mode']

        cmd_str = "%s OBE_ID=%s OBE_MODE=%s %s" % (cmdname.upper(),
                                                   obe_id, obe_mode,
                                                   self.fmtParams(actuals))
        self.logger.info("EXECAB: %s" % (cmd_str))

        subsys = '%s_%s' % (obe_id, obe_mode)

        classInfo = self.getFactory(cmdname, subsys=subsys)

        task = classInfo.klass(**actuals)
        return self.run(task)

    def get_param_aliases(self, aliaslist):
        # Form a status dictionary of items to fetch
        statusDict = {}
        for varname, alias in aliaslist:
            # If no parameter supplied to override default...
            if self.params[varname] == None:
                statusDict[alias] = '##NODATA##'

        # Fetch the items all in one go
        fetchDict = self.fetch(statusDict)

        # Substitute the results back into the parameter vars
        for varname, alias in aliaslist:
            if alias in fetchDict:
                self.params[varname] = fetchDict[alias]

    def thaw_closures(self):
        for var, val in self.params.items():
            if isinstance(val, Closure):
                self.params[var] = val.thaw()

    def enter_block(self):
        with self.tlock:
            # Insert a new "stack frame" for the block we are entering
            frame = Bunch.Bunch(asynclist=[])
            self._stack.insert(0, frame)

    def add_asynctask(self, task):
        with self.tlock:
            frame = self._stack[0]
            task.init_and_start(self)
            frame.asynclist.append(task)

    def exit_block(self):
        with self.tlock:
            frame = self._stack.pop(0)

        asynclist = frame.asynclist
        # wait for all pending asynchronous tasks to complete.
        self.logger.info("Waiting on pending asynchronous tasks")
        while len(asynclist) > 0:

            self.check_state()

            for task in asynclist:
                try:
                    #self.logger.debug("waiting on %s" % task)
                    res = task.wait(timeout=0.0001)

                    # task finished, remove from pending tasks
                    self.logger.debug("task %s finished." % task)
                    asynclist.remove(task)

                #except g2Task.TimeoutError:
                except Task.TaskTimeout:
                    # task still running, keep waiting
                    continue

    def get_frames(self, instname, frametype, count):
        count = int(count)
        frames = self.getFrames(instname, frametype, count)
        return '%s:%04d' % (frames[0], len(frames))

    def get_frame(self, instname, frametype):
        frames = self.getFrames(instname, frametype, 1)
        return frames[0]

    def fmtParams(self, params):
        res = []
        keys = list(params.keys())
        # TODO: show keys in order they were in command line!
        keys.sort()
        for key in keys:
            val = params[key]
            val_str = str(val)

            # Check for spaces in value string and quote if necessary
            if (' ' in val_str) and (not val_str.startswith('"')):
                val_str = ('"%s"' % val_str)

            res.append('%s=%s' % (key.upper(), val_str))

        return ' '.join(res)

    def execute(self):
        # Do preprocessing section
        self.do_pre()

        # Notify that we are done executing the preprocessing section,
        # and do not proceed until last postprocessing section is done.
        if self.sklock:
            self.sklock.acquire()

        self.setMy(main_start=time.time())

        # Execute the main processing section.
        try:
            self.do_main()

            self.setMy(main_end=time.time())

            # Execute the postprocessing section
            res = self.do_post()

        finally:
            if self.sklock:
                self.sklock.release()

#END
