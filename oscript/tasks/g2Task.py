#
# g2Task.py -- Base classes for Gen2 tasks.
#
# E. Jeschke
# B. Bon
#
# Better error messages should be added, in particular to identify the
# source of errors.  See TCSintTask.start() for an example.   BB
#
import sys, time
import threading

from g2base import Task, Bunch
from g2base.remoteObjects import remoteObjects as ro
from g2base.remoteObjects import Monitor
from g2cam.status.common import STATNONE, STATERROR


class g2TaskError(Task.TaskError):
    """Base class for exceptions raised by g2Tasks.
    """
    pass

class TimeoutError(Task.TaskTimeout):
    """Raised when we time out waiting on a value.
    """
    pass

class TaskCancel(g2TaskError):
    """Exception generated when a task is cancelled"""
    pass

class status2dict(object):
    """ *****TEMPORARY WORKAROUND*****
    Wrapper for a gen2 status object to provide a dictionary
    interface for the para populator.
    """

    def __init__(self, g2statusObj):
        """g2statusObj is an object that provides a fetchOne() method.
        """
        self.status = g2statusObj

    # See optimization in DotParaFiles.DotParaFileParser.resolveStatusItems
    def fetch(self, statusDict):
        d = self.status.fetch(statusDict)
        statusDict.update(d)
        return statusDict

    def __getitem__(self, key):
        return self.status.fetchOne(key)

    def has_key(self, key):
        return True


class frame2dict(object):
    """ *****TEMPORARY WORKAROUND*****
    Wrapper for a gen2 frame server to provide a dictionary
    interface for the para populator.
    """

    def __init__(self, g2frameObj):
        """g2frameObj is an object that provides a getFrames() method.
        """
        self.frameSvc = g2frameObj

    def __getitem__(self, key):
        try:
            #self.frameSvc.logger.info("key = %s" % str(key))
            (instname, frametype, reqcount) = key
            if reqcount != None:
                count = int(reqcount)
            else:
                count = 1

            frames = self.frameSvc.getFrames(instname, frametype, count)

            # Should return (count) frames
            assert count == len(frames), \
                   g2TaskError("Number of frames allocated (%d) does not match request (%d)" % (len(frames), count))

            start_frame = frames[0]
            if reqcount == None:
                return start_frame
            else:
                return "%s:%04d" % (start_frame, count)

        except IndexError:
            raise g2TaskError("Bad frame fetch arguments: %s" % str(key))

    def has_key(self, key):
        return True


class g2Task(Task.Task):
    """Base class for all Gen2 tasks.  Provides convenience methods and
    abstracts details about how underlying subsystems communicate and
    synchronize.
    """

    def __init__(self, **kwdargs):

        super(g2Task, self).__init__()

        #self.params = Bunch.caselessDict(kwdargs)
        self.params = Bunch.Bunch(caseless=True, **kwdargs)

        self.monitor = None
        # Parent task can set this (or add to it) explicitly to determine
        # which values will be copied when it calls initialize() on a child
        # task.
        self.extend_shares(['alloc', 'logger', 'monitor', 'threadPool',
                            'shares', 'validator', 'channels'])

        # Maps used to populate default parameters
        self.statusMap = status2dict(self)
        self.frameMap = frame2dict(self)

        self.sleep_interval = 0.01

    def waitOn(self, tag, timeout=None):
        """Wait on a value reported through the monitor.  _tag_ gives a
        dot-separated path to the value.  Optional value _timeout_ gives a
        time to wait (in seconds) for the event to occur, otherwise the
        task times out.
        """
        # wait on any is more efficient than wait on all
        return self.waitOnAny([tag], timeout=timeout)

    def waitOnAll(self, tags, timeout=None):

        if hasattr(self, 'ev_cancel'):
            eventlist = [ self.ev_cancel ]
        else:
            self.logger.warn("No cancel event for task '%s'" % str(self))
            eventlist = []

        self.logger.debug("WAITING for ALL tags in: %s" % (str(tags)))
        # Returns dict of values
        try:
            res = self.monitor.getitem_all(tags, timeout=timeout,
                                           eventlist=eventlist)
            self.logger.debug("RESUMED for ALL tags in: %s" % (str(tags)))
            return res

        except Monitor.EventError as e:
            raise TaskCancel("Task cancelled!")
        except Monitor.TimeoutError as e:
            raise TimeoutError(str(e))

    def waitOnAny(self, tags, timeout=None):

        if hasattr(self, 'ev_cancel'):
            eventlist = [ self.ev_cancel ]
        else:
            self.logger.warn("No cancel event for task '%s'" % str(self))
            eventlist = []

        self.logger.debug("WAITING for ANY tags in: %s" % (str(tags)))
        try:
            res = self.monitor.getitem_any(tags, timeout=timeout,
                                           eventlist=eventlist)
            self.logger.debug("RESUMED for ANY tags in: %s" % (str(tags)))
            return res

        except Monitor.EventError as e:
            raise TaskCancel("Task cancelled!")
        except Monitor.TimeoutError as e:
            raise TimeoutError(str(e))

    def waitOnMy(self, key, timeout=None):
        """Wait on a value reported through the monitor.  _key_ gives a
        dot-separated subpath to the value, with the assumed prefix being
        this task's tag.
        Optional value _timeout_ gives a time to wait (in seconds) for
        the event to occur, otherwise the task times out.
        """
        tag = ("%s.%s" % (self.tag, key))

        return self.waitOn(tag, timeout=timeout)

    def waitOnMyAny(self, keys, timeout=None):

        tags = ['%s.%s' % (self.tag, key) for key in keys]
        return self.waitOnAny(tags, timeout=timeout)

    def waitOnMyAll(self, keys, timeout=None):
        tags = ['%s.%s' % (self.tag, key) for key in keys]
        return self.waitOnAll(tags, timeout=timeout)

    def waitOnMyTrans(self, key, timeout=None, reqtags=None):
        # TODO: see if we can just make waitOnMy do this
        d = self.waitOnMy(key, timeout=timeout)

        # Returns a dict of all items found for this transaction
        trans = self.monitor.getitems_suffixOnly(self.tag)
        if type(trans) != dict:
            raise g2TaskError("Non-dict result for monitor fetch of subtag '%s': %s" % (
                key, str(trans)))

        if reqtags:
            for subtag in reqtags:
                if subtag not in trans:
                    raise g2TaskError("Transaction missing required subtag '%s': %s" % (
                        subtag, str(trans)))

        return Bunch.Bunch(trans)

    def waitOnMyDone(self, timeout=None):
        """Like waitOnMy, but for the specific key of 'done'.
        Most transactions to external subsystems will synchronize to this.
        """
        key = 'done'
        d = self.waitOnMy(key, timeout=timeout)

        # Returns a dict of all items found for this transaction
        trans = self.monitor.getitems_suffixOnly(self.tag)
        if type(trans) != dict:
            trans = {}

        # Extract subsystem message and result
        msg = trans.get('msg', "[no subsystem message returned]")
        self.logger.debug("transaction %s: msg=%s" % \
                          (self.tag, msg))
        return trans

    def setMy(self, **kwdargs):
        """Set keyword values in my task's monitor entry.
        """
        self.monitor.setvals(self.channels, self.tag, **kwdargs)

    def start(self):
        super(g2Task, self).start()

        self.setMy(task_start=self.starttime)

    def initialize(self, parentTask, **kwdargs):
        tag = super(g2Task, self).initialize(parentTask, **kwdargs)

        return tag

    def done(self, result, **kwdargs):
        if self.ev_done.isSet():
            return self.result

        endtime = time.time()
        self.logger.debug("done called: %s result=%s" % (
                self.tag, str(result)))
        # If task raised an exception, then task officially failed
        # else it is considered a success
        if isinstance(result, Exception):
            code = 1
            if isinstance(result, TimeoutError):
                code = 2
            elif isinstance(result, TaskCancel):
                code = 3

            self.setMy(task_code=code, task_error=str(result),
                       task_end=endtime)
        else:
            self.setMy(task_code=0, task_end=endtime)

        # NOTE: if we could call this BEFORE the above then we could
        # use self.endtime, but there is a race condition somwehere?
        res = super(g2Task, self).done(result, **kwdargs)

        self.logger.debug("Task finishing: %s" % (self.tag))
        return res

    def cond_create_state(self):
        if not hasattr(self, 'ev_cancel'):
            self.ev_cancel = threading.Event()
            self.ev_cancel.clear()

        if not hasattr(self, 'ev_pause'):
            self.ev_pause = threading.Event()
            self.ev_pause.set()

    def check_state(self):
        """Method that should check for pause, cancellation, or
        any other preemption event.
        """
        if hasattr(self, 'ev_cancel') and self.ev_cancel.isSet():
            raise TaskCancel("Task %s: task has been cancelled!" % (
                self))

        if hasattr(self, 'ev_pause'):
            self.ev_pause.wait()

    def pause(self):
        self.ev_pause.clear()

    def resume(self):
        self.ev_pause.set()

    def cancel(self):
        self.ev_cancel.set()
        time.sleep(0)
        self.resume()

    def populate(self, parakey):
        """Populate my parameters.  Modifies self.params to fill in
        defaults, etc.  Nothing is returned.
        """
        return self.validator.populate(parakey, self.params,
                                       statusMap=self.statusMap,
                                       frameMap=self.frameMap)

    def validate(self, parakey):
        """Validate my parameters.  Checks self.params against values
        defined in the PARA definition and raises an exception if there
        are any violations.  Nothing is returned.
        """
        return self.validator.validate(parakey, self.params)

    def convert(self, parakey, **kwdargs):
        """Convert my parameters (self.params) according to the formats
        specified in the PARA definition.  Alters self.params.

        Possible keyword args are passed on to the validator.
        They are:
        - nop: a value to test against to convert NOPs (best left
          as the default) and
        - subst_nop: a value to substitute for NOP in the conversion
        """
        return self.validator.convert(parakey, self.params, **kwdargs)

    def format(self, parakey, supress_quotation=False):
        """Format my parameters (self.params) for output as strings.
        Returns a new dict with the formatted parameters.
        """
        return self.validator.format(parakey, self.params,
                                     supress_quotation=supress_quotation)

    def params2str(self, parakey):
        return self.validator.params2str(parakey, self.params)

    def getParamDefaults(self, params):
        """Resolve default parameters that are based on status values
        or other external subsystems.
        """
        # Build up a dictionary of all status values we need to fetch
        statusDict = {}
        items = []
        for name in params:
            name = name.lower()
            try:
                val = self.params[name]
            except KeyError as e:
                raise g2TaskError("No parameter exists with name '%s'" % (
                    name))

            # If this is a status reference, then fetch the status item
            if type(val) == str:
                if val.startswith('!'):
                    alias = val[1:].upper()
                    statusDict[alias] = 0
                    items.append((name, alias))

        # If there are any status values, then fetch the lot and fill in
        # the parameters with the values.
        if len(items) > 0:
            statusDict = self.fetch(statusDict)
            for (name, alias) in items:
                self.params[name] = statusDict[alias]

    def getFrames(self, instname, frametype, count):
        """Get a list of frames.
        """
        if 'frames' not in self.alloc:
            raise g2TaskError("Frame service is not allocated.")

        self.logger.debug("Invoking frames.getFrames(%s, %s, %d)" % \
                          (instname, frametype, count))
        (code, result) = self.alloc['frames'].getFrames(instname, frametype, count)
        if code != ro.OK:
            raise g2TaskError("Error invoking frame service: %s" % (
                str(result)))

        framelist = result
        self.logger.debug("Frame service: framelist=%s" % (framelist))

        return framelist

    def fetchOne(self, statusAlias):
        """Get a single status value.
        """
        if 'status' not in self.alloc:
            raise g2TaskError("status service is not allocated.")

        result = self.alloc['status'].fetchOne(statusAlias)
        #? self.logger.debug("status fetchOne: %s=%s" % (statusAlias, str(result)))

        if result == STATNONE:
            self.logger.warn("fetchOne(%s) returned STATNONE" % (
                statusAlias))
        if result == STATERROR:
            self.logger.warn("fetchOne(%s) returned STATERROR" % (
                statusAlias))

        return result

    def fetch(self, statusDict):
        """Get multiple status values.
        """
        if 'status' not in self.alloc:
            raise g2TaskError("status service is not allocated.")

        self.logger.debug("Invoking status.fetch(%s)" % (str(statusDict)))
        start_time = time.time()

        resultDict = self.alloc['status'].fetch(statusDict)

        self.logger.debug("status fetch (%.3f s): %s" % (
                time.time() - start_time, str(resultDict)))

        for statusAlias in resultDict.keys():
            result = resultDict[statusAlias]
            if result == STATNONE:
                self.logger.warn("fetch(%s) returned STATNONE" % (
                    statusAlias))
            if result == STATERROR:
                self.logger.warn("fetch(%s) returned STATERROR" % (
                    statusAlias))

        return resultDict

    def store(self, statusDict):
        """Store status values.
        """
        if 'status' not in self.alloc:
            raise g2TaskError("Status service is not allocated.")

        self.logger.debug("Invoking status.store(%s)" % (str(statusDict)))
        result = self.alloc['status'].store(statusDict)

        return result

    def getFactory(self, className, subsys=None):
        """Get a task class from the Task Manager.
        """
        if 'taskmgr' not in self.alloc:
            raise g2TaskError("TaskManager service is not allocated.")

        result = self.alloc['taskmgr'].getFactory(className, subsys=subsys)
        return result

    def sleep(self, duration):
        """Sleep efficiently and responding to appropriate external
        events.
        TODO: should this be moved into Task.py?
        """
        cur_time = time.time()
        time_end = cur_time + duration

        self.logger.debug("Sleeping interval, remaining: %f sec..." % \
                              (time_end - cur_time))

        while (cur_time < time_end):
            self.check_state()

            #time.sleep(0)

            self.ev_cancel.wait(min(self.sleep_interval, time_end - cur_time))
            cur_time = time.time()

        self.logger.debug("Wakeup!")

    def get_obcp_code(self, instrument):
        ''' get 3 character obcp code '''
        if instrument is not None:
            ''' If instrument name passed explicitly, then try to look
                 up the right instrument code '''
            try:
                # instrument name COMMON is exception. if so, assign 'CMN'
                if instrument.upper() == 'COMMON':
                    inscode = 'CMN'
                else:
                    inscode = self.insconfig.getCodeByName(instrument)
                self.logger.debug("inscode<%s>" % inscode )

            except KeyError:
                raise g2TaskError("bad instrument name <%s>" % (instrument))

        else:
            # Otherwise, look up the currently allocated instrument
            instrument = self.fetchOne('FITS.SBR.MAINOBCP' )
            inscode = self.insconfig.getCodeByName(instrument)
            if inscode.startswith('#'):
                raise g2TaskError("No instrument allocated!")

        return inscode

    def get_tmname(self):
        """Get a task class from the Task Manager.
        """
        if 'taskmgr' not in self.alloc:
            raise g2TaskError("TaskManager service is not allocated.")

        result = self.alloc['taskmgr'].getName()
        return result

    def get_svcname(self, pfx):
        """Get the service name of the particular instance we are using.
        e.g. get_svcname('integgui') => 'integgui0'
        """
        for name in self.alloc.keys():
            if name.startswith(pfx):
                return name

        raise g2TaskError("'%s' service is not allocated." % (pfx))

    def get_sk(self, cmdName, obe_id, obe_mode):
        """Get a skeleton file task from the Task Manager.
        """
        return self.getFactory(cmdName, subsys=('%s_%s' % (obe_id.upper(),
                                                           obe_mode.upper())))

    def runSequence(self, taskList):
        return self.run(Sequence(taskList))

    def runConcurrent(self, taskList):
        return self.run(Concurrent(taskList))


class Sequence(Task.SequentialTaskset, g2Task):

    def __init__(self, taskList, **kwdargs):
        Task.SequentialTaskset.__init__(self, taskList)
        g2Task.__init__(self, **kwdargs)


class Concurrent(Task.ConcurrentAndTaskset, g2Task):

    def __init__(self, taskList, **kwdargs):
        Task.ConcurrentAndTaskset.__init__(self, taskList)
        g2Task.__init__(self, **kwdargs)


class INSintTask(g2Task):
    """Generic base task for sending a string command to an instrument.
    """

    def __init__(self, svcname, fmtstr, parakey, **kwdargs):
        """Parameters:
        _svcname_: interface name to talk to (e.g. 'INSint9')
        _fmtstr_: formatting string for creating actual instrument
                   command string
        _parakey_: para file checking key
        _kwdargs_: keyword arguments that will be substituted into
        the _fmtstr_ template.

        The resulting string is sent to the instrument.
        """
        self.svcname = svcname
        self.fmtstr = fmtstr
        self.parakey = parakey
        self.cmd_str = ''

        super(INSintTask, self).__init__(**kwdargs)

    def start(self):
        self.logger.debug("Task starting: %s" % self.tag)
        self.setMy(task_start=time.time())

        # Populate, convert and validate parameters if we have a parakey
        # defined
        try:
            if self.parakey:
                self.populate(self.parakey)
                self.convert(self.parakey)
                self.validate(self.parakey)

        except Exception as e:
            self.done(g2TaskError("Parameter validation error: %s" % (
                        str(e))))

        # Format the command string
        try:
            # Format the parameters for output as strings
            str_params = self.format(self.parakey)

            self.cmd_str = self.fmtstr % str_params

        except Exception as e:
            self.done(g2TaskError("Command/parameter formatting error: %s" % (
                        str(e))))

        # Send command string to instrument
        #self.logger.debug("Sending %s to %s" % (self.cmd_str, self.svcname))
        try:
            self.alloc[self.svcname].send_cmd(self.tag, self.cmd_str)

        except KeyError:
            self.done(g2TaskError("Subsystem not allocated: '%s'" % (
                        self.svcname)))

    def wait(self, timeout=None):
        """Wait on instrument command completion.
        """
        # wait on 'done' flag for this task
        trans = self.waitOnMyDone(timeout=timeout)

        # INSint subsystem returns result code via 'end_result'
        res = trans.get('result', -1)
        msg = trans.get('msg', '[No result message]')

        if (type(res) != int) or (res != 0):
            #raise g2TaskError("Instrument command (%s) failed; res=%d msg=%s" % (
            #    self.cmd_str, res, msg))
            res = g2TaskError("Instrument command (%s) failed; res=%d msg=%s" % (
                self.cmd_str, res, msg))

        return self.done(res)


class TCSintNativeTask(g2Task):

    def __init__(self, svcname, cmdString, **kwdargs):
        self.cmd_str = cmdString
        self.svcname = svcname

        super(TCSintNativeTask, self).__init__(**kwdargs)

    def start(self):
        self.logger.debug("Task starting: %s" % self.tag)
        self.setMy(task_start=time.time())

        # Send command string to TCSint subsystem
        try:
            self.alloc[self.svcname].send_native_cmd(self.tag, self.cmd_str)

        except KeyError:
            self.done(g2TaskError("Subsystem not allocated: '%s'" % (
                        self.svcname)))

    def wait(self, timeout=None):
        """Wait on TCS command completion.
        """
        # wait on 'done' flag for this task
        trans = self.waitOnMyDone(timeout=timeout)

        # TCS subsystem returns result code via 'result'
        res = trans.get('result', -1)
        msg = trans.get('msg', '[No result message]')

        if (type(res) != int) or (res != 0):
            res = g2TaskError("Telescope command (%s) failed; res=%d msg=%s" % (
                self.cmd_str, res, msg))

        return self.done(res)


# class TCSintTask(g2Task):

#     def __init__(self, svcname, fmtstr, parakey, **kwdargs):
#         """Parameters:
#         _svcname_: interface name to talk to (e.g. 'TSC')
#         _fmtstr_: formatting string for creating actual telescope
#                    command string
#         _parakey_: para file checking key
#         _kwdargs_: keyword arguments that will be substituted into
#         the _fmtstr_ template.

#         The resulting string is sent to the TCSint subsystem.
#         """
#         self.svcname = svcname
#         self.fmtstr = fmtstr
#         self.parakey = parakey
#         self.cmd_str = ''

#         super(TCSintTask, self).__init__(**kwdargs)


#     def start(self):
#         self.logger.debug("Task starting: %s" % self.tag)
#         self.setMy(task_start=time.time())

#         # Populate, convert and validate parameters if we have a parakey
#         # defined
#         try:
#             if self.parakey:
#                 self.populate(self.parakey)
#                 self.convert(self.parakey)
#                 self.validate(self.parakey)

#         except Exception, e:
#             raise g2TaskError("%s parameter validation error: %s" % (
#                 (self.parakey, str(e))))

#         # Format the command string
#         try:
#             # Format the parameters for output as strings
#             str_params = self.format(self.parakey)

#             self.cmd_str = self.fmtstr % str_params

#         except Exception, e:
#             raise g2TaskError("%s command/parameter formatting error: %s" % (
#                 (self.parakey, str(e))))

#         # Send command string to TCSint subsystem
#         try:
#             self.alloc[self.svcname].send_cmd(self.tag, self.cmd_str)

#         except KeyError:
#             raise g2TaskError("Subsystem not allocated: '%s'" % (
#                 self.svcname))


#     def wait(self, timeout=None):
#         """Wait on TCS command completion.
#         """
#         # wait on 'done' flag for this task
#         trans = self.waitOnMyDone(timeout=timeout)

#         # TCSint subsystem returns result code via 'result'
#         res = trans.get('result', -1)
#         msg = trans.get('msg', '[No result message]')

#         if (type(res) != int) or (res != 0):
#             res = g2TaskError("Telescope command (%s) failed; res=%d msg=%s" % (
#                     self.cmd_str, res, msg))

#         self.done(res)
#         return res
