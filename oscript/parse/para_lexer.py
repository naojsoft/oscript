"""
para_lexer.py -- SOSS PARA file lexer
"""
import logging

from ply import lex

from g2base import Bunch

lex_tab_module = 'PARA_scan_tab'

#===================================================#
# PARA file Lexer
#===================================================#

class paraScanError(Exception):
    pass

class paraScanner(object):

    tokens = ('EQ', 'LPAREN', 'RPAREN', 'COMMA', 'NEWLINE',
              'ID', 'STR', 'QSTR', 'LSTR', 'FSTR', 'REGREF',
              'ALIASREF', 'FUNCREF', 'LCONT', 'COMMENT',
              )

    reserved = set([
        'DEFAULT', 'SET', 'TYPE',
        'STATUS',  'NOP', 'FORMAT',
        'MIN',     'MAX', 'CASE'
        ])

    t_ignore = ' \t'

    #t_BSTR     = r'\[[\w\d ]+\]'                        # Bracketed String(can contain WS)
    t_FSTR     = r'%([+\-]?[\d]*(\.\d*)?)?[hlL]?[sdf]'  # Formatting string for numerals
    t_REGREF   = r'@[\w_][\w\d_]*'                      # 'Register' reference
    t_ALIASREF = r'![\w_][\w\d_\.]*'                    # 'Status'   reference
    t_FUNCREF  = r'\&[\w_][\w\d_\.]+\[[\s\w\d_]+\]'      # 'Function' reference

    def t_STR(self, t):
        r'[a-zA-Z0-9_\.+\-\^]+'
        if self.isTokenAnID:
            self.isTokenAnID = False
            t.type = 'ID'
            return t
        return t

    # Quoted string will not be an ID
    def t_QSTR(self, t):
        r'"[^"]*"'
        # Just strip off the quotes
        t.value = t.value[1:-1]
        return t

    # List string is yet another kind of string
    def t_LSTR(self, t):
        r'\[[^\]]*\]'
        # Just strip off the quotes
        t.value = t.value[1:-1]
        return t

    def t_LPAREN(self, t):
        r'\('
        self.isTokenWithinParenthesis = True
        self.isTokenAnID = True
        return t

    # within the parentheses, the keywords can appear
    # on the right hand side of the equal sign.
    def t_RPAREN(self, t):
        r'\)'
        self.isTokenWithinParenthesis = False
        self.isTokenAnID = False
        return t

    def t_COMMA(self, t):
        r','
        if self.isTokenWithinParenthesis:
            self.isTokenAnID = True
        return t

    def t_EQ(self, t):
        r'='
        if self.isTokenWithinParenthesis:
            self.isTokenAnID = False
        return t

    def t_COMMENT(self, t):
        r'\#.*\n'
        t.lineno += 1

    def t_NEWLINE(self, t):
        r'\n+'
        t.lineno += t.value.count("\n")
        self.isTokenAnID = True
        return t

    def t_LCONT(self, t):
        r'\\\n'
        t.lineno += 1

    def t_error(self, t):
        self.logger.error("Illegal character in input '%s'" % (t.value[0]))
        t.skip(1)

    def build(self):
        self.lexer = lex.lex(object=self, debug=self._debug,
                             lextab=self._lextab)

    def __init__(self, logger=None, debug=False, lextab=lex_tab_module):

        if not logger:
            logger = logging.getLogger('para.lexer')
        self.logger = logger
        self._debug = debug
        self._lextab = lextab
        self.lexer = None

        # these variables are used to determine
        # if the token we are looking is an ID
        self.isTokenAnID = True
        self.isTokenWithinParenthesis = False

        self.build()
        self.reset()

    def reset(self, lineno=1):
        self.errors = 0
        self.errinfo = []
        self.lexer.lineno = lineno

    def getTokens(self):
        return self.tokens

    # For compatibility with ply.yacc
    def token(self):
        return self.lexer.token()

    # For compatibility with ply.yacc
    def input(self, input):
        return self.lexer.input(input)

    def tokenize(self, buf, startline=1):
        # Reset lexer state
        self.reset(lineno=startline)

        self.lexer.input(buf)
        res = []
        while True:
            tok = self.lexer.token()
            if not tok:
                break
            res.append(tok)

        #return (self.errors, res, self.errinfo)
        return res


    def scan_buf(self, buf):

        tokens = self.tokenize(buf)

        res = Bunch.Bunch(tokens=tokens, errors=self.errors,
                          errinfo=self.errinfo)
        return res


    def scan_file(self, parapath):

        with open(parapath, 'r') as in_f:
            buf = in_f.read()

        res = self.scan_buf(buf)
        res.filepath = parapath

        return res
