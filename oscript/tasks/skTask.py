#
# Legacy Skeleton File Handling.
#
# E. Jeschke
#
"""
Legacy Skeleton File (Abstract Command) handling.
"""

import sys, os, glob, time
#from importlib.util import spec_from_loader, module_from_spec
import types
import threading
import queue as Queue
import logging
import traceback

from g2base import Bunch, Task
from g2base.remoteObjects import remoteObjects as ro

import oscript.parse.sk_common as sk_common
import oscript.parse.sk_interp as sk_interp
from oscript.parse.para_parser import NOP
from oscript.tasks import g2Task


class ExecError(sk_interp.skError):
    pass

class ParseExecError(ExecError):
    pass

class skUserException(Task.UserTaskException):
    pass


# Global environment in which skeleton file <Parameter> sections
# are evaluated
global_env = {
    'nop':  NOP,
    }

def force(val):
    if isinstance(val, sk_common.Closure):
        return val.thaw()
    else:
        return val


class myIssueAST(sk_common.IssueAST):

    def issue_exec(self, ast):
        res = super(myIssueAST, self).issue_exec(ast)
        return self.tag_node(ast, res)

    def tag_node(self, ast, res):
        return "<div class=%d>%s</div class=%d>" % (
            ast.serial_num, res, ast.serial_num)


##############################################################
# EXECUTOR
##############################################################

class skExecutorTask(g2Task.g2Task):

    def __init__(self, queue, sklock=None,
                 ev_quit=None, ev_pause=None, ev_cancel=None,
                 timeout=0.01, waitflag=True):

        # Queue for tasks to the dispatcher
        self.queue = queue

        # Lock used to synchronize access to skeleton task critical sections
        self.sklock = sklock

        # Events to terminate the dispatcher
        if not ev_quit:
            ev_quit = threading.Event()
        self.ev_quit = ev_quit

        # Events used to cancel and pause tasks
        if not ev_cancel:
            ev_cancel = threading.Event()
        self.ev_cancel = ev_cancel
        if not ev_pause:
            ev_pause = threading.Event()
        self.ev_pause = ev_pause
        self.ev_pause.set()

        # For mutex between the dispatcher tasks
        self.lock = threading.RLock()

        # poll interval on queue
        self.timeout = timeout

        # Wait for results before starting next task?
        self.waitflag = waitflag

        super(skExecutorTask, self).__init__()


    def execute(self):
        self.count = 0
        self.totaltime = 0
        #self.cond_create_state()

        self.logger.debug("Executor task starting")
        self.extend_shares(['ev_cancel', 'ev_pause', 'sklock'])

        while not self.ev_quit.isSet():
            try:
                task = self.queue.get(block=True, timeout=self.timeout)
                self.task = task

                task.add_callback('resolved', self.child_done)

                self.lock.acquire()
                try:
                    self.count += 1
                finally:
                    self.lock.release()

                # Clear cancel event for this executor
                self.ev_cancel.clear()
                try:
                    task.initialize(self)

                    self.logger.debug("Starting task '%s'" % str(task))
                    task.start()

                    if self.waitflag:
                        self.logger.debug("Waiting for task '%s'" % str(task))
                        res = task.wait()

                        self.logger.debug("Task %s terminated with result %s" % (
                                          (str(task), str(res))))
                        #self.release_sklock()

                except Exception as e:
                    errmsg = "Task '{}' terminated with exception: {}".format(
                        str(task), str(e))
                    if isinstance(e, g2Task.TaskCancel):
                        self.logger.error(errmsg)
                    else:
                        # include stack trace in log
                        self.logger.error(errmsg, exc_info=True)

                    # If task raised exception then it didn't call done
                    task.done(e, noraise=True)

                    self.release_sklock()

            except Queue.Empty:
                # No task available.  Continue trying to get one.
                continue


        # TODO: should we wait for self.count > 0?
        self.logger.debug("Executor task terminating")

        return self.result


    def child_done(self, task, result):
        self.lock.acquire()
        try:
            self.count -= 1
            self.totaltime += task.getExecutionTime()
            self.result = result
        finally:
            self.lock.release()


    def release_sklock(self):
        # Release the sklock, in case the task died in the middle
        # of the skeleton file, while holding the lock.
        try:
            if self.sklock._is_owned():
                self.logger.info("Releasing sklock.")
                self.sklock.release()
        except:
            pass


    def flush(self):
        # Flush queue of pending tasks
        self.logger.debug("Flushing queue.")
        while True:
            try:
                self.queue.get(block=False)
            except Queue.Empty:
                break


    def cancel(self):
        self.flush()

        #super(skExecutorTask, self).cancel()
        g2Task.g2Task.cancel(self)

        self.release_sklock()


    def addTask(self, task):
        self.queue.put(task)


####################################################################
# Generic skeleton language interpretation task
####################################################################
#
class interpTask(g2Task.g2Task):
    """Task class for interpreting a SOSS language fragment.
    Typically, this class would be invoked indirectly via skTask or
    execTask classes.
    """

    def __init__(self, ast, sk_bank, params, ast_default_params=None):
        """Takes an abstract syntax tree (ast), a skeleton file
        bank object (skbank) and initial parameters.  Interprets the ast.
        params are assumed to be a dict of closures or evaluated parameters.
        Optional parameter ast_default_params is an ast of default
        parameter settings.
        """
        self.sk_bank = sk_bank
        self.ast = ast
        self.name = ast.tag
        self.ast_default_params = ast_default_params

        # (This will save params to self.params)
        super(interpTask, self).__init__(**params)


    def execute(self):
        self.cond_create_state()

        # Set up environment for evaluator
        # TODO: should global_env come from sk_bank?--probably
        variable_resolver = sk_interp.VariableResolver({})
        register_resolver = sk_interp.RegisterResolver()
        # Will use status lookup in g2Task base class
        status_resolver = sk_interp.StatusResolver(self)
        # Will use frame lookup in g2Task base class
        frame_source = sk_interp.FrameSource(self)

        # Create expression evaluator
        self.eval = sk_interp.Evaluator(variable_resolver, register_resolver,
                                        status_resolver, frame_source,
                                        self.logger)

        # If there is a default_params_ast, then close over it before
        # setting actual params into the evaluator
        # TODO: any chance ast_default_params needs to be decoded?
        if self.ast_default_params:
            self.eval.set_params(self.ast_default_params, close=True)

        # Now substitute replacement parameters
        self.eval.set_vars(self.params, nonew=True)

        # Create decoder.  FOR NOW...share eval with decoder
        self.decoder = sk_interp.Decoder(self.eval, self.sk_bank, self.logger)

        self.check_state()

        # Decode AST and substitute params;
        # should be no vars left after this pass
        new_ast = self.decoder.decode(self.ast, self.eval)

        # Record serial number of this AST execution
        self.sk_id = '%d.%d' % (os.getpid(), new_ast.serial_num)

        # Send out specially formatted/encoded version of the AST for
        # the skTask monitor to display and update in real time
        myissue = myIssueAST()
        data = [myissue.issue(new_ast)]
        # If our creator stored a command string, prepend it for
        # documentation
        if hasattr(self, 'cmd_str'):
            data.insert(0, '# %s' % self.cmd_str)
        ast_time = time.time()
        data.insert(0, time.strftime('# %Y-%m-%d %H:%M:%S',
                                     time.localtime(ast_time)))
        buf = '\n'.join(data)

        try:
            buf = ro.compress(buf.encode('latin1'))
            enc_buf = ro.binary_encode(buf)
            self.setMy(ast_buf=enc_buf, ast_id=self.sk_id, ast_time=ast_time)
            buf = enc_buf = None
        except Exception as e:
            buf = enc_buf = None
            self.logger.warn("Failed to compress AST; no command monitoring in integgui2")

        # Ugh--get decoded AST string rep again and log it
        decode_res = new_ast.AST2str()
        self.logger.info("=== DECODING RESULT ===\n%s" % (
            decode_res))

        return self.interpret(new_ast, self.eval)


    def interpret(self, ast, eval):
        """Generid top-level method to interpret an ast node.
        """
        # Check if we are being asked to terminate, etc.
        self.check_state()

        self.logger.debug("Interpreting AST=%s" % str(ast))
        try:
            # Look up the method for interpreting this kind of AST.
            interp_method = getattr(self, 'interp_%s' % ast.tag)

        except AttributeError:
            # ==> There is no function "interp_XXX" for the tag XXX of the ast.
            raise ExecError("No interpretation for AST node '%s'" % ast.tag)

        if not callable(interp_method):
            raise ExecError("No method for interpreting parse object '%s'" % ast.tag)

        # Call the method on this ast
        return interp_method(ast, eval)


    def interp_command_section(self, ast, eval):
        """Interpret skeleton file.  Takes an ast for the preprocessing
        section, the main processing section and the postprocessing section
        and executes them.
        """
        assert (ast.tag == 'command_section') and (len(ast.items) == 3), \
               ParseExecError("Badly formed command_section ast: %s" % str(ast))

        # Extract the preprocessing ASTs from the decoded skeleton file
        # ast.
        (pre_ast, main_ast, post_ast) = ast.items

        # Execute the preprocessing section
        self.interpret(pre_ast, eval)

        # Notify that we are done executing the preprocessing section,
        # and do not proceed until last postprocessing section is done.
        if self.sklock:
            self.sklock.acquire()

        self.setMy(main_start=time.time())

        # Execute the main processing section.
        try:
            self.interpret(main_ast, eval)

            self.setMy(main_end=time.time())

            # Execute the postprocessing section
            res = self.interpret(post_ast, eval)

        finally:
            if self.sklock:
                self.sklock.release()

        return res


    def interp_if_list(self, ast, eval):
        """Interpret an IF statement.

        IF <pred-exp>
            <then-clause>
        ELIF <pred-exp>
            <then-clause>
        ...
        ELSE
            <else-clause>
        ENDIF

        The AST for this is a variable number of 'cond' ribs
           ((pred1-exp, then1-exp), ..., (predN-exp, thenN-exp))

        An ELSE clause, if present, is represented by a final
        (True, then-exp) rib.
        """
        assert (ast.tag == 'if_list'), \
               ParseExecError("Badly formed IF expression: %s" % str(ast))

        # Iterate over the set of cond ribs, execute the first then-part
        # for whose predicate evaluates to true.
        for cond_ast in ast.items:
            assert (cond_ast.tag == 'cond') and (len(cond_ast.items) == 2), \
                   ParseExecError("Badly formed COND rib: %s" % str(cond_ast))
            (pred_ast, then_ast) = cond_ast.items

            # ==> bodies of then-sections are always cmdlist's
            assert (then_ast.tag == 'cmdlist'), \
                   ParseExecError("Badly formed THEN ast: %s" % str(then_ast))

            if pred_ast == True:
                # ELSE clause
                return self.interp_cmdlist(then_ast, eval)

            #assert (pred_ast.tag == 'expression') and  (pred_ast.tag == 'dyad')
            #       ParseExecError("Badly formed predicate ast: %s" % str(pred_ast))

            res = eval.eval(pred_ast)
            if eval.isTrue(res):
                return self.interp_cmdlist(then_ast, eval)

        # See Note [1]
        return 0


    def interp_while(self, ast, eval):
        """Interpret a WHILE statement.

        WHILE <pred-exp> {
            <statements>
        }

        The AST for this looks like
           (pred-exp, block)
        """
        assert (ast.tag == 'while') and (len(ast.items) == 2), \
               ParseExecError("Badly formed WHILE expression: %s" % str(ast))

        (pred_ast, body_ast) = ast.items

        not_done = True
        while not_done:

            # Check if we are being asked to terminate, etc.
            self.check_state()

            res = eval.eval(pred_ast)
            not_done = eval.isTrue(res)
            if not_done:
                try:
                    self.interp_block(body_ast, eval)

                except skUserException as e:
                    val_s = str(e).lower()
                    if val_s == 'break':
                        not_done = False
                        self.logger.info("Breaking loop.")
                    elif val_s == 'continue':
                        self.logger.info("Continuing loop.")
                        continue
                    else:
                        raise

        # See Note [1]
        return 0


    def interp_catch(self, ast, eval):
        """Interpret a CATCH statement.

        CATCH var {
            <statements>
        }

        The AST for this looks like
           (var, block)
        """
        assert (ast.tag == 'catch') and (len(ast.items) == 2), \
               ParseExecError("Badly formed CATCH expression: %s" % str(ast))

        (var, body_ast) = ast.items

        try:
            res = self.interp_block(body_ast, eval)

        except Exception as e:
            self.logger.info("Caught exception in CATCH: %s" % (
                str(e)))
            res = e

        d = {var: res}
        eval.registers.set(**d)
        return 0


    def interp_raise(self, ast, eval):
        """Interpret a RAISE statement.

        RAISE expr
        """
        assert (ast.tag == 'raise') and (len(ast.items) == 1), \
               ParseExecError("Badly formed RAISE expression: %s" % str(ast))

        exp_ast = ast.items[0]
        res = eval.eval(exp_ast)

        raise skUserException(str(res))


    def interp_calc(self, ast, eval):
        """Interpret a CALC statement.

        CALC expr
        """
        assert (ast.tag == 'calc') and (len(ast.items) == 1), \
               ParseExecError("Badly formed CALC expression: %s" % str(ast))

        exp_ast = ast.items[0]
        res = eval.eval(exp_ast)
        return res


    def interp_exec(self, ast, eval):
        """Interpret a device-dependent command task.
        """
        assert (ast.tag == 'exec') and (len(ast.items) == 4), \
               ParseExecError("Badly formed EXEC ast: %s" % str(ast))

        (subsys_ast, cmdname_ast, params_ast, resvar_ast) = ast.items

        # Evaluate DD command parameters
        cmdname = eval.eval(cmdname_ast)
        subsys = eval.eval(subsys_ast)
        params = eval.eval_params(params_ast)

        varname = None
        if resvar_ast != None:
            varname = eval.eval(resvar_ast)
            assert isinstance(varname, str), \
                   ParseExecError("Badly formed varname: %s" % str(varname))

        # Look up simple task class for DD command
        classInfo = self.getFactory(cmdname, subsys=subsys)

        #str(classInfo.klass)
        cmd_str = "EXEC %s %s %s" % (subsys, cmdname.upper(),
                                     self.fmtParams(params))
        self.logger.info("EXECDD: %s" % (cmd_str))

        # Instantiate task
        task = classInfo.klass(**params)

        # Run task and return result
        try:
            #res = self.run(task)
            task.initialize(self)

            # Notify interested parties of linkage between this AST node and
            # this task.  We have to initialize() before we have a valid tag.
            self.setMy(ast_num=ast.serial_num, ast_str=cmd_str,
                       ast_track=task.tag, ast_id=self.sk_id,
                       ast_time=time.time())
            task.start()
            res = task.wait()

        except Exception as e:
            if varname == None:
                raise e
            res = 1

        self.logger.debug("EXECDD: %.3f sec (%s)" % (
                task.totaltime, cmd_str))

        # If user used a "var=" type feature with this command
        # then store the result
        if varname:
            kwdargs = { varname: res }
            eval.registers.set(**kwdargs)
        return res


    def interp_set(self, ast, eval):
        """Interpret a SET statement.  This statement stores values into
        the @ variables.
        """
        assert (ast.tag == 'set') and (len(ast.items) == 1), \
               ParseExecError("Badly formed SET ast: %s" % str(ast))

        params_ast = ast.items[0]
        params = eval.eval_params(params_ast)

        eval.registers.set(**params)

        # Return result
        return 0


    def interp_proc_call(self, ast, eval):
        """Interpret a procedure call.
        """
        assert (ast.tag == 'proc_call') and (len(ast.items) == 2), \
               ParseExecError("Badly formed procedure call ast: %s" % str(ast))

        regref, params_ast = ast.items
        # get function
        fn = eval.registers.get(regref[1:])

        # evaluate parameters
        args, kwdargs = eval.eval_args(params_ast)
        self.logger.info("fn=%s args=%s kwdargs=%s" % (fn, args, kwdargs))

        return fn(*args, **kwdargs)

    def interp_proc(self, ast, eval):
        """Interpret a procedure definition.
        """
        assert (ast.tag == 'proc') and (len(ast.items) == 3), \
               ParseExecError("Badly formed procedure definition ast: %s" % str(ast))

        name_ast, varlist, body_ast = ast.items
        varlist = varlist.items
        varDict = Bunch.caselessDict(dict.fromkeys(varlist))

        name = eval.eval(name_ast)

        def _interp_proc(*args, **kwdargs):
            # check that all params are defined
            self.logger.info("%s called with args=%s kwdargs=%s varDict=%s" % (
                name, args, kwdargs, varDict))

            d = {}

            # process regular args
            for i in range(len(args)):
                d[varlist[i]] = args[i]

            # check keyword params
            for var in kwdargs.keys():
                if var not in varDict:
                    raise ExecError("Parameter '%s' not defined in procedure '%s'" % (
                        var, name))
            d.update(kwdargs)

            # extend environment with new parameters
            eval2 = eval.clone()
            eval2.registers.push(d)

            # interpret body in this envt
            return self.interpret(body_ast, eval2)

        kwdargs = { name: _interp_proc }
        eval.registers.set(**kwdargs)


    def interp_let(self, ast, eval):
        """Interpret a LET statement.
        """
        assert (ast.tag == 'let') and (len(ast.items) == 2), \
               ParseExecError("Badly formed LET ast: %s" % str(ast))

        params_ast, body_ast = ast.items
        # eval parameters
        params = eval.eval_params(params_ast)

        eval2 = eval.clone()
        eval2.registers.push(params)
        res = self.interpret(body_ast, eval2)
        return res


    def interp_import(self, ast, eval):
        """Interpret a IMPORT statement.
        """
        assert (ast.tag == 'import') and (len(ast.items) == 2), \
               ParseExecError("Badly formed IMPORT ast: %s" % str(ast))

        modname, varlist_ast = ast.items

        # Get variable list
        assert varlist_ast.tag == 'varlist', \
               ParseExecError("Badly formed IMPORT ast: %s" % str(ast))
        varlist = varlist_ast.items

        module = __import__(modname)
        index = Bunch.caselessDict(module.__dict__)

        d = { var: index[var] for var in varlist }
        # this is like a global setting in the skeleton
        eval.registers.set(**d)

        return None


    def interp_abscmd(self, ast, eval):
        """Interpret a abstract command task.
        """
        assert (ast.tag == 'abscmd') and (len(ast.items) == 2), \
               ParseExecError("Badly formed abstract command ast: %s" % str(ast))

        (cmdname_ast, params_ast) = ast.items

        # Evaluate abstract command parameters
        cmdname = eval.eval(cmdname_ast)

        # Close over parameters here, and then force just
        # OBE_ID and OBE_MODE, which we need to know to look up the
        # skeleton file
        # ast should have already been decoded, so we are just mimicking
        # via closures the string substitution that occurs in the SOSS
        # decoder
        #params = eval.eval_params(params_ast)
        params = eval.close_params(params_ast)

        try:
            obe_id = force(params['obe_id'])
            del params['obe_id']

        except KeyError:
            raise ExecError("No OBE_ID specified in '%s' command" % cmdname)

        try:
            obe_mode = force(params['obe_mode'])
            del params['obe_mode']

        except KeyError:
            raise ExecError("No OBE_MODE specified in '%s' command" % cmdname)

        # N.B. subsys must agree with the one generated in
        # TaskManager.loadAbsCmds()
        subsys = sk_interp.get_subsys(obe_id, obe_mode)
        cmdname = cmdname.lower()

        cmd_str = "%s OBE_ID=%s OBE_MODE=%s %s" % (
            cmdname.upper(), obe_id, obe_mode, self.fmtParams(params))
        self.logger.info("EXECAB: %s" % (cmd_str))

        # Look up task class for abstract command
        classInfo = self.getFactory(cmdname, subsys=subsys)
        #self.logger.debug("class is: %s" % str(classInfo.klass))

        # Instantiate task
        task = classInfo.klass(**params)
        # NOTE: THIS MUST BE A form of interpTask (e.g. skTask);
        # to call any other kind of task use EXEC <subsys> COMMAND ...
        # assert isinstance(task, skTask), \
        #        ExecError("'%s' task is not an skTask: %s" % (
        #     cmdname, repr(task)))
        task.cmd_str = cmd_str

        # Run task and return result
        res = self.run(task)

        self.logger.debug("EXECAB: %.3f sec (%s)" % (
                task.totaltime, cmd_str))
        return res


    def block_exec(self, ast, eval):
        self.logger.debug("block_exec")
        res = 0
        asynctasks = []

        # Iterate through the sub-elements of this ast, running them as
        # tasks.  For commands and blocks marked asynchronous, start them
        # and add them to the wait set (asynctasks) otherwise run the task
        # and wait for it to finish.
        for sub_ast in ast.items:
            # Check if we should be interrupted
            self.check_state()

            self.logger.debug("sub_ast is %s" % str(sub_ast))

            if sub_ast.tag == 'nop':
                continue

            elif sub_ast.tag == 'return':
                res = None    # 0?
                if len(sub_ast.items) > 0:
                    exp_ast = sub_ast.items[0]
                    res = eval.eval(exp_ast)

                break

            elif sub_ast.tag == 'async':
                # Substatement marked asynchronous.  Make a task, start it
                # and add it to the asynctasks list
                sub_sub_ast = sub_ast.items[0]

                task = self.mkTask(sub_sub_ast.name, self.interpret,
                                   sub_sub_ast, eval)
                asynctasks.append(task)

                # Start executing task and continue
                task.init_and_start(self)

            # Anything not tagged asynchronous is assumed synchronous
            else:
                # Unfold interpretation of sync elements
                if sub_ast.tag == 'sync':
                    sub_ast = sub_ast.items[0]

                # Run this task and iterate
                task = self.mkTask(sub_ast.name, self.interpret,
                                   sub_ast, eval)
                res = self.run(task)

        # We've finished all synchronous tasks.  Now wait for all pending
        # asynchronous tasks to complete.
        while len(asynctasks) > 0:

            self.check_state()

            for task in asynctasks:
                try:
                    #self.logger.debug("waiting on %s" % task)
                    res2 = task.wait(timeout=0.0001)

                    # task finished, remove from pending tasks
                    self.logger.debug("task %s finished." % task)
                    asynctasks.remove(task)

                #except g2Task.TimeoutError:
                except Task.TaskTimeout:
                    # task still running, keep waiting
                    continue

        return res


    def interp_block(self, ast, eval):
        assert (ast.tag == 'block'), \
               ParseExecError("block ast has wrong tag: %s" % str(ast))
        return self.block_exec(ast, eval)

    def interp_block_merge(self, ast, eval):
        assert (ast.tag == 'block_merge'), \
               ParseExecError("block-merge ast has wrong tag: %s" % str(ast))
        return self.block_exec(ast, eval)


    def interp_cmdlist(self, ast, eval):
        assert (ast.tag == 'cmdlist'), \
               ParseExecError("cmdlist ast has wrong tag: %s" % str(ast))
        return self.block_exec(ast, eval)


    # Without a lot more unfolding, we are going to need one of these
    def interp_nop(self, ast, eval):
        assert (ast.tag == 'nop'), \
               ParseExecError("nop ast has wrong tag: %s" % str(ast))
        return 0


    def main_start(self):
        """This method is called when we have reached the MAIN_START of
        an abstract command.
        """
        # Wait for access to the critical section of a skeleton file
        # (only one skeleton file can be in execution between MAIN_START
        # and MAIN_END in the normal queue.

        # NOTE: sklock is obtained by "contagion" during the initialize()
        # period from the parent task
        if self.sklock:
            self.sklock.acquire()

        self.setMy(main_start=time.time())
        return 0


    def main_end(self):
        """This method is called when we have reached the MAIN_END of
        an abstract command.
        """
        self.setMy(main_end=time.time())

        if self.sklock:
            self.sklock.release()
        return 0


    def wait(self, timeout=None):
        # skTasks have a different definition of waiting, because task
        # is "done" when we reach :MAIN_END
        trans = self.waitOnMyAny(['task_end', 'main_end'],
                                 timeout=timeout)

        # Is there a value we should be looking for in the transaction?

        return self.done(0)


    def mkTask(self, name, func, *args, **kwdargs):
        """Make a task for recursing into the interpretation, or some other
        internal function.
        """

        class anonTask(g2Task.g2Task):

            def execute(self):
                self.logger.debug("Executing fn %s" % func)
                val = func(*args, **kwdargs)

                self.logger.debug("Done executing fn %s" % func)
                return val

        task = anonTask()
        task.name = name

        return task


    def fmtParams(self, params):
        res = []
        keys = list(params.keys())
        # TODO: show keys in order they were in command line!
        keys.sort()
        for key in keys:
            val = params[key]
            # If this is a closure, then get the syntactical representation
            if isinstance(val, sk_common.Closure):
                val_str = val.ast.AST2str()
            else:
                val_str = str(val)

            # Check for spaces in value string and quote if necessary
            if (' ' in val_str) and (not val_str.startswith('"')):
                val_str = ('"%s"' % val_str)

            res.append('%s=%s' % (key.upper(), val_str))

        return ' '.join(res)


# Due to unfolding in block_exec, we should always catch these?
##     def interp_sync(self, ast):
##         assert (ast.tag == 'sync') and (len(ast.items) == 1), \
##               ParseExecError("malformed sync ast: %s" % str(ast))

##         sub_ast = ast.items[0]

##         return self.execute(sub_ast)


##     def interp_async(self, ast):
##         assert (ast.tag == 'async') and (len(ast.items) == 1), \
##               ParseExecError("malformed async ast: %s" % str(ast))

##         sub_ast = ast.items[0]

##         task = self.mkInterpTask(sub_ast)
##         t.initialize(self)
##         t.start()

##         return 0


class execTask(interpTask):
    """A task to execute a command string on the fly.
    """

    def __init__(self, cmdstr, envstr, sk_bank):
        """Constructor takes a command string (cmdstr), and environment
        string (envstr--an initial list of parameters) and a skeleton file
        bank object (sk_bank).
        """

        self.cmdstr = cmdstr

        # Parse environment string into an AST, raising parse error if
        # necessary
        envstr = envstr.strip()
        if len(envstr) > 0:
            res = sk_bank.param_parser.parse_params(envstr)
            if res[0]:
                raise ParseExecError("Error parsing default parameters '%s': %s" % (
                    envstr, res[2]))

            ast_params = res[1]
            assert (ast_params.tag == 'param_list'), \
                   ParseExecError("Malformed default parameter list '%s': AST=%s" % (envstr, str(ast_params)))

        else:
            ast_params = None

        # Parse command string into an AST, raising parse error if
        # necessary
        res = sk_bank.ope_parser.parse_opecmd(cmdstr)
        if res[0]:
            raise ParseExecError("Error parsing command '%s': %s" % (
                cmdstr, res[2]))

        # Now pull off the cmdlist and execute
        ast = res[1]
        assert (ast.tag == 'cmdlist'), \
               ParseExecError("Error parsing command '%s': %s" % (
            cmdstr, str(e)))

        ast = ast.items[0]

        super(execTask, self).__init__(ast, sk_bank, {},
                                       ast_default_params=ast_params)


class skTask(interpTask):
    """Implements a task to execute an abstract command by interpreting
    a skeleton file.
    """

    def __init__(self, sk_bank, obe_id, obe_mode, cmdname, params):
        """Constructor.  Parameters are a skeleton file bank object
        (sk_bank), an instrument name (obe_id), mode (obe_mode), an
        abstract command name (cmdname) and an initial environment as
        a set of keyword parameters (a dict).

        NOTE: Assumes (params) are already evaluated!
        """

        self.obe_id = obe_id
        self.obe_mode = obe_mode
        self.cmdname = cmdname

        # Look up the AST for this skeleton file from the sk_bank object
        # (the bank contains lazily-parsed ASTs to speed up execution).
        # This returns a bunch that contains the AST, and possibly any
        # errors related to parsing it
        skbunch = sk_bank.lookup(obe_id, obe_mode, cmdname)
        if skbunch.errors > 0:
            try:
                errinfo = skbunch.errinfo
                parse_error = errinfo[0].verbose
            except (KeyError, AttributeError):
                parse_error = ''

            raise ParseExecError("%d errors parsing referent skeleton file '%s':\n%s" % (
                skbunch.errors, skbunch.filepath, parse_error))

        # this shows up in the status variable FITS.<INST>.OBS-MOD
        self._obs_mod = skbunch.header.get('OBS_MOD', obe_mode).upper()

        # Extract the ast and verify it contains a list of default
        # parameters and a body
        ast_skel = skbunch.ast
        assert (ast_skel.tag == 'skeleton') and (len(ast_skel.items) == 2), \
               ParseExecError("Badly formed skeleton ast: %s" % str(ast_skel))
        (ast_default_params, ast_body) = ast_skel.items

        # Rest of the work is done by parent class
        super(skTask, self).__init__(ast_body, sk_bank, params,
                                     ast_default_params=ast_default_params)


    def execute(self):

        # Report our execution to the monitor
        self.setMy(skfile='%s (%s/%s)' % (self.cmdname,
                                          self.obe_id, self.obe_mode))

        statusDict = {}
        if self.obe_id.lower() in ['common']:
            inscode = 'CMN'
        else:
            inscode = self.insconfig.getCodeByName(self.obe_id)

        # If we were started with an OBJECT= parameter, then set the
        # appropriate status variable FITS.<INS>.OBJECT
        if 'object' in self.params:
            statusDict['FITS.%3.3s.OBJECT' % inscode] = force(self.params['object'])

        statusDict['FITS.%3.3s.OBS-MOD' % inscode] = self._obs_mod
        statusDict['FITS.%3.3s.OBS_MOD' % inscode] = self._obs_mod
        self.store(statusDict)

        # Rest of the work is done by parent class
        return super(skTask, self).execute()



####################################################################
# Module level support functions for building collections of
# abstract commands.
####################################################################
#

def abscmd_class_factory(sk_bank, obe_id, obe_mode, cmdname):
    """Makes a task class for the abstract command identified by
    (obe_id, obe_mode, cmdname).  By iterating this function over the set
    of abstract commands for a given instrument and its mode, a complete
    set of abstract command tasks can be generated.  Parsed files
    will be stored into the skeleton bank object (skbank).
    """

    obe_id = obe_id.upper()
    obe_mode = obe_mode.upper()
    cmdname = cmdname.upper()

    # Create a class, and give it the name <INST>_<MODE>_<CMDNAME>
    #klassName = ('%s_%s_%s' % (obe_id, obe_mode, cmdname))
    # Create a class, and give it the name <cmdname>
    klassName = cmdname.lower()

    def init(self, *args, **kwdargs):
        # How can we do this with new-style superclass calls
        #super(klassName, self).__init__(obe_id, obe_mode, cmdname,
        #                                **kwdargs)
        skTask.__init__(self, sk_bank, obe_id, obe_mode, cmdname, kwdargs)

    klass = type(klassName, (skTask, ), {'__init__': init})

    #print "Made class '%s' is %s" % (klassName, str(klass))
    return klass


def build_abscmd_classes(skbase, ins, mode, file, sk_bank=None):
    """
    e.g.  d = build_abscmd_classes('xlib/python/SOSS/SkPara/sk', 'MOIRCS',
                                       'IMAG_AG', '*.sk')
    Dynamically creates a dict of skeleton file interpretation tasks
    (skTask) that implement any abstract commands for the instrument
    and mode.  Takes a base directory of the skeleton files (skbase),
    the instrument name (ins), the instrument mode (mode) and the
    skeleton file name (file).  ins, mode and file can also be wildcarded
    '*'--the files are globbed from the base directory.
    """

    # If no skeleton bank is passed, create a new temporary one
    if sk_bank == None:
        sk_bank = sk_interp.skBank(skbase)

    cmd_dct = {}

    # Glob the directory structure beginning at the base to find out
    # the desired files to parse
    for skpath in glob.glob('%s/%s/sk/%s/%s' % (skbase, ins, mode, file)):
        pfx, skfile = os.path.split(skpath)
        pfx, obe_mode = os.path.split(pfx)
        pfx, skxx = os.path.split(pfx)
        pfx, obe_id = os.path.split(pfx)
        cmdname, ext = os.path.splitext(skfile)

        # Create a task class for this particular combination
        klass = abscmd_class_factory(sk_bank, obe_id, obe_mode, cmdname)
        #print "Made class '%s'" % (str(klass))
        cmd_dct[klass.__name__] = klass

    # Returns a dictionary, indexed by class name
    return cmd_dct


def build_abscmd_module(skbase, obe_id, obe_mode, sk_bank=None):
    """
    e.g.  m = build_abscmd_module('.../', 'MOIRCS','IMAG_AG')
    Dynamically creates a module of skeleton file interpretation tasks
    (skTask) that implement any abstract commands for the obe_id (instrument)
    and obe_mode (mode).  Takes a base directory of the skeleton files,
    the obe_id and the obe_mode as parameters.
    """

    # Configuration
    module_prefix = 'sk_'
    #code_template = """
    #class %s(skTask):
    #    def __init__(self, **params):
    #        super(%s, self).__init__(%s, %s, %s, **params)
    #"""

    # Create the classes
    classDict = build_abscmd_classes(skbase, obe_id, obe_mode, '*.sk',
                                     sk_bank=sk_bank)

    # Create new module with name: sk_<obeid>_<obemode>
    modname = ('%s%s_%s' % (module_prefix, obe_id.upper(), obe_mode.upper()))
    #modspec = spec_from_loader(modname, loader=None)
    #module = module_from_spec(modspec)
    module = types.ModuleType(modname)

    # Add default subsystem
    classDict['SUBSYS'] = sk_interp.get_subsys(obe_id, obe_mode)

    # Lovely Python introspection: dynamically add classes to the new module
    module.__dict__.update(classDict)

    # Ta-daaaa!
    return module


def getModes(skbase, obe_id):
    """Takes the base directory of the skeleton files and a single
    obe_id as parameters.  Returns a list of tuples of the form
    (obe_id, obe_mode) for every mode available for that obe_id.
    """

    modes = []

    for skpath in glob.glob('%s/%s/sk/*' % (skbase, obe_id)):
        # skip things that aren't folders
        if not os.path.isdir(skpath):
            continue

        pfx, obe_mode = os.path.split(skpath)
        modes.append((obe_id, obe_mode))

    return modes


def getModesList(skbase, obe_list):
    """Takes the base directory of the skeleton files and a list of
    obe_ids as parameters.  Returns a list of tuples of the form
    (obe_id, obe_mode) for every mode available for those obe_ids.
    """

    modes = []

    for obe_id in obe_list:
        for skpath in glob.glob('%s/%s/sk/*' % (skbase, obe_id)):
            # skip things that aren't folders
            if not os.path.isdir(skpath):
                continue

            pfx, obe_mode = os.path.split(skpath)
            modes.append((obe_id, obe_mode))

    return modes


def build_abscmd_modules(skbase, obe_list, sk_bank=None):
    """
    e.g.  m = build_abscmd_modules('.../', ['IRCS', 'COMMON'])
    Returns a list of modules dynamically created for the list of
    obe_ids, where each module implements the abstract commands for
    a particular instrument and mode.
    """

    modules = []

    for (obe_id, obe_mode) in getModesList(skbase, obe_list):

            modules.append(build_abscmd_module(skbase, obe_id, obe_mode,
                                               sk_bank=sk_bank))

    return modules


#END
