"""
sk_parser.py -- oscript ("skeleton") file parser
"""
import sys
import logging

import ply.yacc as yacc
from ply.lex import LexToken

from oscript.parse import sk_common
from oscript.parse.sk_common import ASTNode
from oscript.parse.param_parser import paramParser, skParseError

from g2base import Bunch

##################################################################
# !!! NOTE !!! NOTE !!! NOTE !!!
# *** When you update this file, you need to update the class
#     IssueAST in sk_common accordingly!! ***
##################################################################


class opeParser(paramParser):

    def __init__(self, lexer, logger=None,
                 debug=False, parsetab='ope_command_parse_tab'):
        super(opeParser, self).__init__(lexer, logger=logger,
                                        debug=debug, parsetab=parsetab)

        self.tokens.remove('UMINUS')
        self.tokens.extend(['EXEC'])

    # --- .OPE file commands ---

    def p_opecmd(self, p):
        """opecmd : dd_cmd
                  | abs_cmd
        """
        p[0] = ASTNode('cmdlist', p[1])

    def p_abscmd(self, p):
        """abs_cmd : factor param_list"""
        p[0] = ASTNode('abscmd', p[1], p[2], )

    def p_ddcmd(self, p):
        """dd_cmd : EXEC factor factor param_list"""
        p[0] = ASTNode('exec', p[2], p[3], p[4], None)

    def build(self):
        self.ope_parser = yacc.yacc(module=self, start='opecmd',
                                    debug=self._debug,
                                    tabmodule=self._parsetab,
                                    errorlog=self.logger)

    def parse_opecmd(self, buf, startline=1):

        # Initialize module level error variables
        self.reset(lineno=startline)

        try:
            ast = self.ope_parser.parse(buf, lexer=self.lexer)

        except Exception as e:
            # capture traceback?  Yacc tracebacks aren't that useful
            ast = ASTNode('ERROR: %s' % str(e))
            # verify errors>0
            assert(self.errors > 0)

        try:
            assert(ast.tag == 'cmdlist')

        except AssertionError:
            # ??  We're being silent like normal parsing
            pass

        return (self.errors, ast, self.errinfo)


    def parse_opebuf(self, opebuf):

        # Get the constituent parts of a skeleton file:
        # header, parameter list, command part
        (hdrbuf, prmbuf, cmdbuf, startline) = sk_common.get_opeparts(opebuf)

        (errors, ast_params, errinfo) = self.parse_opecmd(cmdbuf,
                                                          startline=startline)

        # This will hold the results
        res = Bunch.Bunch(errors=errors, errinfo=errinfo)

        # make readable errors
        if errors > 0:
            #print("ERRINFO = ", errinfo)
            for errbnch in errinfo:
                errbnch.verbose = sk_common.mk_error(cmdbuf, errbnch, 1)

        return res

    def parse_opefile(self, opepath):

        with open(opepath, 'r') as in_f:
            opebuf = in_f.read()

        res = self.parse_opebuf(opebuf)
        res.filepath = opepath

        return res


class skParser(paramParser):

    def __init__(self, lexer, logger=None,
                 debug=False, parsetab='sk_parse_tab'):
        super(skParser, self).__init__(lexer, logger=logger,
                                       debug=debug, parsetab=parsetab)

        self.tokens.remove('UMINUS')
        self.tokens.extend(['START', 'MAINSTART', 'MAINEND', 'END',
                            'SEMICOLON', 'LCURBRACKET', 'RCURBRACKET',
                            'STAR_SUB', 'IF', 'ELIF', 'ELSE', 'ENDIF',
                            'STAR_IF', 'STAR_ELIF', 'STAR_ELSE', 'STAR_ENDIF',
                            'STAR_SET', 'ASN', 'STAR_FOR', 'IN', 'STAR_ENDFOR',
                            'WHILE', 'LET', 'DEF', 'FROM', 'IMPORT',
                            'CATCH', 'RAISE', 'RETURN', 'EXEC'])

    def p_program1(self, p):
        """program : command_section"""
        p[0] = p[1]

    def p_command_section(self, p):
        """command_section : preamble mainpart endpart"""
        p[0] = ASTNode('command_section', p[1], p[2], p[3])

    def p_preamble1(self, p):
        """preamble : START statements"""
        p[0] = p[2]

    def p_preamble2(self, p):
        """preamble : START"""
        p[0] = ASTNode('nop')

    def p_mainpart1(self, p):
        """mainpart : MAINSTART statements MAINEND"""
        p[0] = p[2]

    def p_mainpart2(self, p):
        """mainpart : MAINSTART MAINEND"""
        p[0] = ASTNode('nop')

    def p_endpart1(self, p):
        """endpart : statements END"""
        p[0] = p[1]

    def p_endpart2(self, p):
        """endpart : END"""
        p[0] = ASTNode('nop')

    def p_statements(self, p):
        """statements : statement"""
        p[0] = p[1]

    ## def p_statements1(self, p):
    ##     """statements : statements statement"""
    ##     p[0] = p[1]
    ##     p[0].append(p[2])

    def p_statement(self, p):
        """statement : command_list"""
        p[0] = p[1]

    def p_command_list1(self, p):
        """command_list : command_list async
                        | command_list sync
        """
        p[0] = p[1]
        p[0].append(p[2])

    def p_command_list2(self, p):
        """command_list : command_list special_form
                        | command_list abs_command
        """
        p[0] = p[1]
        p[0].append(p[2])

    def p_command_list3(self, p):
        """command_list : async
                        | sync
                        | abs_command
                        | special_form
        """
        p[0] = ASTNode('cmdlist', p[1])

    def p_command_list4(self, p):
        """command_list : empty
        """
        #p[0] = ASTNode('cmdlist', ASTNode('nop'))
        p[0] = ASTNode('nop')

    def p_special_form(self, p):
        """special_form : if_list
                        | star_if_list
                        | star_for_loop
                        | while_loop
                        | catch
                        | raise
                        | return
                        | star_set_stmnt
                        | let_stmnt
                        | set_stmnt
                        | proc_defn
                        | import_stmnt
        """
        p[0] = ASTNode('cmdlist', p[1])

    def p_async(self, p):
        """async : exec_command COMMA
                 | abs_command COMMA
                 | command_block COMMA
                 | proc_call COMMA
                 | while_loop COMMA
                 | let_stmnt COMMA
                 | catch COMMA
        """
        p[0] = ASTNode('async', p[1])

    def p_sync(self, p):
        """sync : exec_command SEMICOLON
                | abs_command SEMICOLON
                | command_block SEMICOLON
                | proc_call SEMICOLON
                | while_loop SEMICOLON
                | let_stmnt SEMICOLON
                | catch SEMICOLON
        """
        p[0] = ASTNode('sync', p[1])

    def p_command_block(self, p):
        """command_block : LCURBRACKET command_list RCURBRACKET"""
        p[0] = ASTNode('block', p[2])
        # avoid making a block inside a block
        p[0].items = p[2].items

    def p_command_exec(self, p):
        """exec_command : EXEC factor factor param_list"""
        p[0] = ASTNode('exec', p[2], p[3], p[4], None)

    def p_command_exec1(self, p):
        """exec_command : ID ASSIGN EXEC factor factor param_list"""
        p[0] = ASTNode('exec', p[4], p[5], p[6], p[1])

    def p_command_abs(self, p):
        """abs_command : STAR_SUB factor param_list"""
        p[0] = ASTNode('star_sub', p[2], p[3], )

    # TODO: can this be combined with the *IF rules?
    def p_if_list1_0(self, p):
        """if_list : IF expression ENDIF"""
        # empty then and ELSE clauses
        p[0] = ASTNode('nop')

    def p_if_list1_1(self, p):
        """if_list : IF expression command_list ENDIF"""
        p[0] = ASTNode('if_list', ASTNode('cond', p[2], p[3]))

    def p_if_list1_1_1(self, p):
        """if_list : IF expression command_list ELSE ENDIF"""
        # Empty ELSE clause
        p[0] = ASTNode('if_list', ASTNode('cond', p[2], p[3]))

    def p_if_list1_2(self, p):
        """if_list : IF expression command_list ELSE command_list ENDIF"""
        p[0] = ASTNode('if_list', ASTNode('cond', p[2], p[3]),
                       ASTNode('cond', True, p[5]))

    def p_if_list1_3(self, p):
        """if_list : IF expression command_list elif_list ENDIF"""
        p[0] = ASTNode('if_list', ASTNode('cond', p[2], p[3]))
        for i in p[4]:
            p[0].append(i)
        #p[0].append(p[4])

    def p_if_list1_4(self, p):
        """if_list : IF expression command_list elif_list ELSE command_list ENDIF"""
        p[0] = ASTNode('if_list', ASTNode('cond', p[2], p[3]))
        for i in p[4]:
            p[0].append(i)
        p[0].append(ASTNode('cond', True, p[6]))

    def p_elif(self, p):
        """elif : ELIF expression command_list"""
        p[0] = ASTNode('cond', p[2], p[3])

    def p_elif_list(self, p):
        """elif_list : elif"""
        p[0] = [p[1]]

    def p_elif_list2(self, p):
        """elif_list : elif_list elif"""
        p[0] = p[1]
        p[0].append(p[2])

    # TODO: can this be combined with the IF rules?
    def p_star_if_list1_1(self, p):
        """star_if_list : STAR_IF expression STAR_ENDIF"""
        # empty then and ELSE clauses
        p[0] = ASTNode('nop')

    def p_star_if_list1_2(self, p):
        """star_if_list : STAR_IF expression command_list STAR_ENDIF"""
        p[0] = ASTNode('star_if', ASTNode('cond', p[2], p[3]))

    def p_star_if_list2_1(self, p):
        """star_if_list : STAR_IF expression command_list STAR_ELSE STAR_ENDIF"""
        # Empty ELSE clause
        p[0] = ASTNode('star_if', ASTNode('cond', p[2], p[3]))

    def p_star_if_list2_2(self, p):
        """star_if_list : STAR_IF expression command_list STAR_ELSE command_list STAR_ENDIF"""
        p[0] = ASTNode('star_if', ASTNode('cond', p[2], p[3]),
                       ASTNode('cond', True, p[5]))

    def p_star_if_list3_1(self, p):
        """star_if_list : STAR_IF expression command_list star_elif_list STAR_ENDIF"""
        p[0] = ASTNode('star_if', ASTNode('cond', p[2], p[3]))
        for i in   p[4]:
            p[0].append(i)
        #p[0].append(p[4])

    def p_star_if_list3_2(self, p):
        """star_if_list : STAR_IF expression command_list star_elif_list STAR_ELSE command_list STAR_ENDIF"""
        p[0] = ASTNode('star_if', ASTNode('cond', p[2], p[3]))
        for i in p[4]:
            p[0].append(i)
        p[0].append(ASTNode('cond', True, p[6]))

    def p_star_elif(self, p):
        """star_elif : STAR_ELIF expression command_list"""
        p[0] = ASTNode('cond', p[2], p[3])

    def p_star_elif_list(self, p):
        """star_elif_list : star_elif_list star_elif"""
        p[0] = p[1]
        p[0].append(p[2])

    def p_star_elif_list2(self, p):
        """star_elif_list : star_elif"""
        p[0] = [p[1]]

    def p_star_set_stmnt1(self, p):
        """star_set_stmnt : STAR_SET set_flags param_list"""
        p[0] = ASTNode('star_set', p[3], p[2])

    def p_star_set_stmnt2(self, p):
        """star_set_stmnt : STAR_SET param_list"""
        p[0] = ASTNode('star_set', p[2], None)

    def p_set_stmnt(self, p):
        """set_stmnt : ASN kwd_params"""
        p[0] = ASTNode('set', p[2])

    def p_set_flags1(self, p):
        """set_flags : set_flags set_flag"""
        p[0] = p[1]
        p[0].append(p[2])

    def p_set_flags2(self, p):
        """set_flags : set_flag"""
        p[0] = [p[1]]

    def p_set_flag(self, p):
        """set_flag : SUB ID"""
        p[0] = p[2]

    def p_star_for_loop1(self, p):
        """star_for_loop : STAR_FOR expression idlist IN expression command_list STAR_ENDFOR"""
        p[0] = ASTNode('star_for', p[2], p[3], p[5], p[6])

    def p_star_for_loop2(self, p):
        """star_for_loop : STAR_FOR expression idlist IN command_list STAR_ENDFOR"""
        p[0] = ASTNode('star_for', p[2], p[3], None, p[5])

    def p_star_for_loop3(self, p):
        """star_for_loop : STAR_FOR expression idlist IN STAR_ENDFOR"""
        # empty loop
        p[0] = ASTNode('star_for', p[2], p[3], None, ASTNode('nop'))

    def p_while_loop1(self, p):
        """while_loop : WHILE expression command_block"""
        p[0] = ASTNode('while', p[2], p[3])

    def p_let(self, p):
        """let_stmnt : LET kwd_params IN command_block"""
        p[0] = ASTNode('let', p[2], p[4])

    def p_proc_defn1(self, p):
        """proc_defn : DEF ID LPAREN varlist RPAREN command_block"""
        p[0] = ASTNode('proc', p[2], p[4], p[6])

    def p_import(self, p):
        """import_stmnt : FROM QSTR IMPORT varlist"""
        p[0] = ASTNode('import', p[2], p[4])

    def p_catch1(self, p):
        """catch : CATCH ID command_block"""
        p[0] = ASTNode('catch', p[2], p[3])

    def p_raise(self, p):
        """raise : RAISE expression"""
        p[0] = ASTNode('raise', p[2])

    def p_return(self, p):
        """return : RETURN expression"""
        p[0] = ASTNode('return', p[2])

    def p_return2(self, p):
        """return : RETURN"""
        p[0] = ASTNode('return')

    def p_idlist1(self, p):
        """idlist : expressions"""
        p[0] = ASTNode('idlist', p[1])

    def p_varlist1(self, p):
        """varlist : ID"""
        p[0] = ASTNode('varlist', p[1])

    def p_varlist2(self, p):
        """varlist : varlist COMMA ID"""
        p[0] = p[1]
        p[0].append(p[3])

    def p_expressions(self, p):
        """expressions : expressions expression"""
        p[0] = p[1]
        p[0].append(p[2])

    def p_expressions2(self, p):
        """expressions : expression"""
        p[0] = [p[1]]

    def build(self):
        self.parser = yacc.yacc(module=self, start='program',
                                debug=self._debug, tabmodule=self._parsetab,
                                errorlog=self.logger)
        self.p_parser = paramParser(self.lexer, logger=self.logger)
        self.p_parser.build()
        self.param_parser = self.p_parser.param_parser

    def parse(self, buf, startline=1):

        # Initialize module level error variables
        self.reset(lineno=startline)

        try:
            ast = self.parser.parse(buf, lexer=self.lexer)
            #print("errors=%d, AST=%s" % (self.errors, ast))

            ## # !!! HACK !!!  MUST FIX PARSER!!!
            ## try:
            ##     print(self.errors, "errors")
            ##     self.errinfo.pop()
            ##     self.errors -= 1
            ##     ast = self.result
            ## except IndexError:
            ##     pass
            ## print(ast)

        except Exception as e:
            # capture traceback?  Yacc tracebacks aren't that useful
            errstr = 'ERROR: %s' % (str(e))
            ast = ASTNode(errstr)
            # verify errors>0 ???
            #assert(self.errors > 0)
            if self.errors == 0:
                self.errors += 1
            self.errinfo.append(Bunch.Bunch(lineno=self.lexer.lexer.lineno,
                                            errstr=errstr,
                                            token=None))
            self.logger.error(errstr)

        return (self.errors, ast, self.errinfo)


    def parse_skbuf(self, buf):

        # Get the constituent parts of a skeleton file:
        # header, parameter list, command part
        (hdrbuf, prmbuf, cmdbuf, startline) = sk_common.get_skparts(buf)
        # print("header", hdrbuf)
        # print("params", prmbuf)
        # print("commands", cmdbuf)

        # Get the header params
        try:
            header, _2, _3 = collect_params(hdrbuf)
        except Exception as e:
            # don't let parsing errors of the header hold us back
            # header is not really used for anything important
            header = {}

        # Make a buffer of the default params in an easily parsable form
        params, param_lst, patterns = collect_params(prmbuf)

        parambuf = ' '.join(param_lst)
        #print(parambuf)

        # Parse default params into an ast.
        (errors, ast_params, errinfo) = self.parse_params(parambuf)
        #print("ast_params:", ast_params.printAST())

        # This will hold the results
        res = Bunch.Bunch(errors=errors, errinfo=errinfo, header=header)

        # make readable errors
        if errors > 0:
            #print("ERRINFO = ", errinfo)
            for errbnch in errinfo:
                errbnch.verbose = sk_common.mk_error(parambuf, errbnch, 1)

        # parse the command part
        (errors, ast_cmds, errinfo) = self.parse(cmdbuf, startline=startline)

        # Append errinfo together
        res.errors += errors
        res.errinfo.extend(errinfo)

        # make readable errors
        for errbnch in errinfo:
            errbnch.verbose = sk_common.mk_error(cmdbuf, errbnch, 10)

        res.params = params
        res.patterns = patterns

        # Finally, glue the params AST and the commands AST together to make
        # "skeleton" node
        res.ast = ASTNode("skeleton", ast_params, ast_cmds)

        # return a bundle of these objects
        return res


    def parse_skfile(self, skpath):

        with open(skpath, 'r') as in_f:
            buf = in_f.read()

        res = self.parse_skbuf(buf)
        res.filepath = skpath

        return res


def collect_params(prmbuf):
    params = {}
    param_lst = []
    patterns = {}

    lines = prmbuf.split('\n')

    while len(lines) > 0:
        line = lines.pop(0).strip()
        # skip comments and blank lines
        if line.startswith('#') or (len(line) == 0):
            continue

        # handle line continuations
        while line.endswith('\\') and (len(lines) > 0):
            line = line[:-1] + lines.pop(0).strip()

        if '=' in line:
            try:
                idx = line.find('=')
                var = line[0:idx].strip().upper()
                val = line[idx+1:].strip()
                if not var.startswith('*'):
                    params[var] = val
                    param_lst.append("%s=%s" % (var, val))
                else:
                    patterns[var[1:]] = val.split(',')

            except Exception as e:
                raise skParseError("Error parsing parameter section: %s" % (str(e)))
    return params, param_lst, patterns
