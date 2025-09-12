####################################################################
# Gen2 Instrument Task Base Classes
####################################################################
#
# E. Jeschke
#
import time
from oscript.parse.para_parser import NOP
from oscript.tasks import g2Task


class Ins2TaskError(g2Task.g2TaskError):
    pass

class Ins2Task(g2Task.g2Task):
    """Base instrument task from which generation 2 interface instrument tasks
    are derived.
    """
    def __init__(self, svcname, cmdname, **kwdargs):
        """Parameters:
        _svcname_: interface name to talk to (e.g. 'SUKA')
        _cmdname_: method name to call
        _kwdargs_: keyword arguments that will be checked.
        """

        self.subsys  = svcname
        self.svcname = svcname
        self.cmdname = cmdname.lower()
        self.parakey = (svcname, cmdname.upper())

        super(Ins2Task, self).__init__(**kwdargs)


    def start(self):
        self.logger.debug("Task starting: %s" % self.tag)
        self.setMy(task_start=time.time())

        # Populate and validate parameters if we have a parakey defined
        try:
            if self.parakey:
                self.populate(self.parakey)
                #self.convert(self.parakey, subst_nop=None)
                self.convert(self.parakey)
                self.validate(self.parakey)

                # Announce our full command string
                try:
                    cmd_str = self.params2str(self.parakey)
                    self.setMy(cmd_str=cmd_str)
                except Exception as e:
                    self.logger.error("Error setting cmd_str: %s" % str(e))

                #self.convert(self.parakey, subst_nop=None)

        except Exception as e:
            raise Ins2TaskError("Parameter validation error: %s" % str(e))

        kwdargs = {}
        kwdargs.update(self.params)

        # Remove keyword args that are NOPs so that they get
        # default values in Python method
        for key, val in list(kwdargs.items()):
            if val == NOP:
                self.logger.debug("removing kwd arg=%s" % (key))
                del kwdargs[key]
        # # Change NOP's to None's
        # for key, val in list(kwdargs.items()):
        #     if val == NOP:
        #         kwdargs[key] = None

        try:
            obj = self.alloc[self.svcname]

        except KeyError:
            raise Ins2TaskError("Subsystem not allocated: '%s'" % (
                    self.svcname))

        # Send command string to instrument
        self.logger.debug("Invoking remote command: %s %s" % (
                self.cmdname, str(kwdargs)))

        # Inform monitor of impending event
        self.setMy(cmd_time=time.time())

        try:
            ack_res = obj.executeCmd(self.subsys, self.tag,
                                     self.cmdname, (), kwdargs)

            self.setMy(ack_time=time.time(), ack_result=0)

        except Exception as e:
            msg = "NACK from subsystem %s: %s" % (self.svcname, str(e))
            self.setMy(ack_time=time.time(), ack_result=-1, ack_msg=msg)
            #self.logger.error(msg)
            raise Ins2TaskError(msg)


    def wait(self, timeout=None):
        """Wait on instrument command completion.
        """
        # wait on 'done' flag for this task
        trans = self.waitOnMyDone(timeout=timeout)

        # INSint subsystem returns result code via 'end_result'
        res = trans.get('result', -1)
        msg = trans.get('msg', '[No result message]')

        if (type(res) != int) or (res != 0):
            ## raise Ins2TaskError("Instrument command failed; res=%d msg=%s" % (
            ##     res, msg))
            res = Ins2TaskError("Instrument command failed; res=%d msg=%s" % (
                res, msg))
        return self.done(res)

#END
