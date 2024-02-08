"""
param_parser.py -- oscript ("skeleton") file base class parser
"""
import sys
import logging

import ply.yacc as yacc
from ply.lex import LexToken

from oscript.parse import sk_lexer
from oscript.parse import sk_common
from oscript.parse.sk_common import ASTNode

from g2base import Bunch

yacc_tab_module = 'param_parse_tab'


##################################################################
# !!! NOTE !!! NOTE !!! NOTE !!!
# *** When you update this file, you need to update the class
#     IssueAST in sk_common accordingly!! ***
##################################################################

class skParseError(sk_common.skError):
    pass

class paramParser(object):

    precedence = (
        ('left', 'AND', 'OR'),
        ('right', 'NOT'),
        ('nonassoc', 'EQ', 'NE', 'GT', 'GE', 'LT', 'LE'),
        ('left', 'ADD', 'SUB'),
        ('left', 'MUL', 'DIV'),
        ('right', 'UMINUS'),         # Ficticious token, unary minus operator
    )

    def __init__(self, lexer, logger=None,
                 debug=False, parsetab=yacc_tab_module):
        super(paramParser, self).__init__()

        if not logger:
            logger = logging.getLogger('sk.parser')
        self.logger = logger
        self.errors = 0
        self.errinfo = []
        self._debug = debug
        self._parsetab = parsetab

        # Share lexer tokens
        self.lexer = lexer
        #tokens = list(lexer.getTokens())
        self.tokens = ['ID', 'ASSIGN', 'NUM', 'IDREF', 'ALIASREF',
                       'OR', 'AND', 'LSTR', 'QSTR', 'REGREF', 'ADD',
                       'UMINUS', 'MUL', 'DIV', 'SUB', 'LT',
                       'GT', 'LE', 'GE', 'EQ', 'NE', 'NOT', 'LPAREN',
                       'RPAREN', 'COMMA', 'GET_F_NO']

    def p_param_list1(self, p):
        """ param_list : empty"""
        p[0] = ASTNode('param_list')

    def p_param_list2(self, p):
        """param_list : param_list key_value_pair"""
        p[1].append(p[2])
        p[0] = p[1]

    def p_key_value_pair(self, p):
        """key_value_pair : ID ASSIGN expression"""
        #p[0] = ASTNode('key_value_pair', p[1].upper(), p[3])
        p[0] = ASTNode('key_value_pair', p[1].lower(), p[3])

    def p_factor1(self, p):
        """factor : NUM"""
        if p[1].find('.') < 0:
            p[0] = ASTNode('number', int(p[1]))
        else:
            p[0] = ASTNode('number', float(p[1]))

    def p_factor2(self, p):
        """factor : IDREF"""
        p[0] = ASTNode('id_ref', p[1][1:])

    def p_factor3(self, p):
        """factor : ALIASREF"""
        p[0] = ASTNode('alias_ref', p[1][1:])

    def p_factor4(self, p):
        """factor : frame_id_ref"""
        p[0] = p[1]


    # This is for reserved keywords used like ordinary strings/ids
    # Grrrr!
    def p_factor6(self, p):
        """ factor : ID
                   | OR
                   | AND
        """
        p[0] = ASTNode('string', p[1])

    def p_factor7(self, p):
        """ factor : LSTR """
        #p[0] = p[1]
        p[0] = ASTNode('lstring', p[1])

    def p_factor8(self, p):
        """ factor : QSTR """
        p[0] = ASTNode('qstring', p[1])

    def p_factor9(self, p):
        """factor : REGREF"""
        p[0] = ASTNode('reg_ref', p[1][1:])

    ## def p_factor_2_1(self, p):
    ##     """factor2 : SUB factor %prec UMINUS"""
    ##     p[0] = ASTNode('monad', p[1], p[2])

    def p_factor_2_2(self, p):
        """factor2 : ADD factor %prec UMINUS"""
        p[0] = p[2]

    ## def p_factor_2_3(self, p):
    ##     """factor2 : factor"""
    ##     p[0] = p[1]

    def p_dyad1(self, p):
        """dyad : expression MUL expression
                | expression DIV expression
                | expression ADD expression
                | expression SUB expression
                | expression LT expression
                | expression GT expression
                | expression LE expression
                | expression GE expression
                | expression EQ expression
                | expression NE expression
                | expression AND expression
                | expression OR expression
        """
        p[0] = ASTNode('dyad', p[1], p[2], p[3])

    def p_monad1(self, p):
        """monad : NOT expression
                 | SUB expression %prec UMINUS
        """
        p[0] = ASTNode('monad', p[1], p[2])

    def p_func_call(self, p):
        """func_call : ID LPAREN arg_list RPAREN"""
        p[0] = ASTNode('func_call', p[1], p[3])

    def p_proc_call(self, p):
        """proc_call : REGREF LPAREN arg_list RPAREN"""
        p[0] = ASTNode('proc_call', p[1], p[3])

    def p_proc_call2(self, p):
        """proc_call : REGREF LPAREN RPAREN"""
        p[0] = ASTNode('proc_call', p[1], None)

    def p_arg_list1(self, p):
        """ arg_list : expression_list COMMA kwd_params"""
        l = list(p[1].items)
        l.extend(p[3].items)
        p[0] = ASTNode('arg_list')
        p[0].items = l

    def p_arg_list2(self, p):
        """ arg_list : expression_list"""
        p[0] = ASTNode('arg_list')
        p[0].items = p[1].items

    def p_arg_list3(self, p):
        """ arg_list : kwd_params"""
        p[0] = ASTNode('arg_list')
        p[0].items = p[1].items

    def p_kwd_params1(self, p):
        """kwd_params : key_value_pair COMMA kwd_params"""
        p[0] = ASTNode('kwd_params', p[1])
        p[0].items.extend(p[3].items)

    def p_kwd_params2(self, p):
        """kwd_params : key_value_pair"""
        p[0] = ASTNode('kwd_params', p[1])

    ## def p_arg_list2(self, p):
    ##     """arg_list : key_value_pair COMMA arg_list"""
    ##     p[0] = ASTNode('arg_list', p[1])
    ##     p[0].items.extend(p[3].items)

    ## def p_arg_list3(self, p):
    ##     """arg_list : key_value_pair"""
    ##     p[0] = ASTNode('arg_list', p[1])

    def p_asnum1(self, p):
        """asnum : LPAREN expression RPAREN"""
        p[0] = ASTNode('asnum', p[2])

    def p_expression1(self, p):
        """expression : monad
                      | dyad
                      | func_call
                      | proc_call
                      | asnum
                      | factor
                      | factor2"""
        p[0] = p[1]

    def p_frame_id_acquisition(self, p):
        """frame_id_ref : GET_F_NO LSTR"""
        p[0] = ASTNode('frame_id_ref', p[2])

    def p_expression_list1(self, p):
        """expression_list : expression"""
        p[0]  = ASTNode('expression_list', p[1])

    def p_expression_list2(self, p):
        """expression_list : expression_list COMMA expression"""
        p[1].append(p[3])
        p[0] = p[1]

    def p_epslion(self, p):
        """empty :"""
        pass

    ## def p_list(self, p):
    ##     """list : LSQRBRACKET expressions RSQRBRACKET"""
    ##     p[0] = ASTNode('list', p[2])

    def p_error(self, arg):

        self.errors += 1
        if isinstance(arg, LexToken):
            errstr = ("Parse error at line %d, token %s ('%s')" % (
                arg.lineno, arg.type, str(arg.value)))
            self.errinfo.append(Bunch.Bunch(lineno=arg.lineno, errstr=errstr,
                                            token=arg))
            self.logger.error(errstr)

            # ? Try to recover to some sensible state
            self.parser.errok()

        else:
            errstr = ("Parse error: %s" % str(arg))
            #print errstr
            self.errinfo.append(Bunch.Bunch(lineno=0, errstr=errstr, token=arg))
            self.logger.error(errstr)

            # ? Try to recover to some sensible state
            self.parser.restart()


    def reset(self, lineno=1):
        self.errors = 0
        self.errinfo = []
        # hack
        self.result = None

        self.lexer.reset(lineno=lineno)


    def build(self):
        self.param_parser = yacc.yacc(module=self, start='param_list',
                                      debug=self._debug,
                                      tabmodule=self._parsetab,
                                      errorlog=self.logger)


    def parse_params(self, buf):
        """Hack routine to parse a bare parameter list.
        """
        # TODO: need separate lexer? parser?

        # Initialize module level error variables
        self.reset(lineno=1)

        try:
            ast = self.param_parser.parse(buf, lexer=self.lexer)

        except Exception as e:
            # capture traceback?  Yacc tracebacks aren't that useful
            ast = ASTNode('ERROR: %s' % str(e))
            # verify errors>0
            #assert(self.errors > 0)

        try:
            assert(ast.tag == 'param_list')

        except AssertionError:
            # ??  We're being silent like normal parsing
            pass

        return (self.errors, ast, self.errinfo)
