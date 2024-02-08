"""
sk_lexer.py -- oscript ("skeleton") file lexer/scanner

"""
import logging
import re

import ply.lex as lex
import ply.yacc as yacc

from g2base import Bunch

from oscript.parse import sk_common

num_re = re.compile(r'^[0-9]+(\.\d*)?$')


class skScanError(sk_common.skError):
    pass

class skScanner(object):

    tokens = (
              'ID',
              #'CONST',
              'NUM',
              'ASSIGN',
              'NEWLINE',
              'COMMENT',
              'LPAREN',
              'RPAREN',
              'LCURBRACKET',
              'RCURBRACKET',
              'LSQRBRACKET',
              'RSQRBRACKET',
              'LCONT',
              'COMMA',
              'SEMICOLON',
              'QSTR',
              'LSTR',
              'IDREF',
              'ALIASREF',
              'REGREF',
              #'LIST',

              'EXEC',
              'LET',

              'ASN',
              'STAR_SET',

              'IF',
              'IN',
              'ELIF',
              'ELSE',
              'ENDIF',

              'STAR_IF',
              'STAR_ELIF',
              'STAR_ELSE',
              'STAR_ENDIF',

              'WHILE',
              'RAISE',
              'DEF',
              'FROM',
              'IMPORT',
              'RETURN',
              'CATCH',

              'STAR_SUB',

              'STAR_FOR',
              'STAR_ENDFOR',
              'GET_F_NO',
              'START',
              'MAINSTART',
              'MAINEND',
              'END',
              # operators
              'MUL',
              'ADD',
              'SUB',
              'DIV',
              # relationals
              'EQ',
              'NE',
              'GT',
              'GE',
              'LT',
              'LE',
              # logicals
              'AND',
              'OR',
              'NOT',
              )

    reserved_map = {
              'EXEC'   : 'EXEC',
              'ASN'    : 'ASN',
              'IF'     : 'IF',
              'AND'    : 'AND',
              'OR'     : 'OR',
              'NOT'    : 'NOT',
              'IN'     : 'IN',
              'ELIF'   : 'ELIF',
              'ELSE'   : 'ELSE',
              'ENDIF'  : 'ENDIF',
              'WHILE'  : 'WHILE',
              'RAISE'  : 'RAISE',
              'CATCH'  : 'CATCH',
              'DEF'    : 'DEF',
              'RETURN' : 'RETURN',
              'FROM'   : 'FROM',
              'IMPORT' : 'IMPORT',
              'LET'    : 'LET',
              ':START'  : 'START',
              ':MAIN_START' : 'MAINSTART',
              ':MAIN_END' : 'MAINEND',
              ':END'    : 'END',
    }

    t_ignore = ' \t'

    t_START     = r'\:START'
    t_MAINSTART = r'\:MAIN_START'
    t_END       = r'\:END'
    t_MAINEND   = r'\:MAIN_END'
    t_NUM       = r'[0-9\.]+(\.\d*)?'
    t_EQ        = r'=='
    t_NE        = r'\!='
    t_GT        = r'\>'
    t_GE        = r'\>='
    t_LT        = r'\<'
    t_LE        = r'\<='
    t_ASSIGN    = r'='
    t_SEMICOLON = r';'
    t_COMMA     = r','
    t_LPAREN    = r'\('
    t_RPAREN    = r'\)'
    t_LCURBRACKET = r'{'
    t_RCURBRACKET = r'}'
    t_LSQRBRACKET = r'\['
    t_RSQRBRACKET = r'\]'
    t_ADD       = r'\+'
    t_SUB       = r'\-'
    t_MUL       = r'\*'
    t_DIV       = r'\/'
    t_GET_F_NO  = r'&GET_F_NO'

    t_STAR_IF     = r'\*IF'
    t_STAR_ENDIF  = r'\*ENDIF'
    t_STAR_ELIF   = r'\*ELIF'
    t_STAR_ELSE   = r'\*ELSE'
    t_STAR_SET    = r'\*SET'
    t_STAR_SUB    = r'\*SUB'
    t_STAR_FOR    = r'\*FOR'
    t_STAR_ENDFOR = r'\*ENDFOR'

    #t_ALIASREF  = r'![\w_][\w\d_\.]*'    # 'Status' reference
    def t_ALIASREF(self, t):
        r'![\w_][\w\d_\.]*'
        # 'Status' reference: strip off the '!'
        #t.value = t.value[1:]
        return t

    #t_IDREF     = r'\$[\w_][\w\d_\.]*'   # 'Variable' reference
    def t_IDREF(self, t):
        r'\$[\w_][\w\d_\.]*'
        # 'Variable' reference: strip off the '$'
        #t.value = t.value[1:]
        return t

    #t_REGREF     = r'\@[\w_][\w\d_\.]*'  # 'Register' reference
    def t_REGREF(self, t):
        r'\@[\w_][\w\d_\.]*'
        # 'Register' reference: strip off the '@'
        #t.value = t.value[1:]
        return t

    def t_ID(self, t):
        #r'''[a-zA-Z0-9][a-zA-Z0-9_\.\:\-]*'''
        r'''[a-zA-Z0-9][a-zA-Z0-9_\.\:]*'''

        # t_NUM unfortunately overlaps with t_ID, due to the bad specification
        # of the OScript language, therefore we check if the item is all number
        # here and convert the token type as necessary.
        if num_re.match(t.value):
            t.type = 'NUM'
            return t

        t.value = t.value.upper()
        #tok = t.value.upper()
        tok = t.value
        if tok in self.reserved_map:
            t.type = self.reserved_map[tok]
            # Convert lower case to upper
            #t.value = tok
        return t

    #(((\"[^\"]*?\")?[^ \t\n\"]+)+)|(((\"[^\"]*?\")[^\t\n\"]*)+)
    ## def t_ID(self, t):
    ##     r'''(((\"[^\"]*?\")?[^ \t\n\"]+)+)|(((\"[^\"]*?\")[^\t\n\"]*)+)'''
    ##     tok = t.value.upper()
    ##     if reserved_map.has_key(tok):
    ##         t.type = reserved_map[tok]
    ##         # Convert lower case to upper
    ##         t.value = tok
    ##     return t

    # Double quoted string
    def t_QSTR(self, t):
        r'"([^"\\\n]|\\(.|\n))*"'
        # Just strip off the quotes
        t.value = t.value[1:-1]
        return t

    # Single quoted string
    def t_SQSTR(self, t):
        r"'([^'\\\n]|\\(.|\n))*'"
        # Just strip off the quotes
        t.value = t.value[1:-1]
        t.type = 'QSTR'
        return t

    # List string is yet another kind of string
    def t_LSTR(self, t):
        r'\[[^\]]*\]'
        # Just strip off the quotes
        t.value = t.value[1:-1]
        return t

    def t_LCONT(self, t):
        r'\\\n'
        #print 'LCONT'
        #t.lineno += 1
        self.lexer.lineno += 1

    def t_COMMENT(self, t):
        r'\#.*\n'
        #t.lineno += 1
        self.lexer.lineno += 1

    ## def t_STAR_SET(self, t):
    ##     r'(?i)\*SET.*\n'
    ##     t.value = t.value[4:-1]
    ##     t.lineno += 1
    ##     return t

    ## def t_SET(self, t):
    ##     r'(?i)SET\s*.*\n'
    ##     t.value = t.value[3:-1]
    ##     t.lineno += 1
    ##     return t

    ## def t_IN(self, t):
    ##     r'(?i)IN\s*.*\n'
    ##     t.value = t.value[2:-1]
    ##     t.lineno += 1
    ##     return t

    def t_NEWLINE(self, t):
        r'\n+'
        #t.lineno += t.value.count('\n')
        self.lexer.lineno += t.value.count('\n')
        #return t

    # Error handling rule
    def t_error(self, t):
        errstr = ("Scan error at line %d, character ('%s')" % (
            t.lineno, t.value[0]))
        #print errstr
        self.errinfo.append(Bunch.Bunch(lineno=t.lineno, errstr=errstr,
                                        token=t))
        self.errors += 1
        #t.skip(1)


    def build(self):
        self.lexer = lex.lex(object=self, reflags=re.IGNORECASE,
                             debug=self._debug, lextab=self._lextab)

    def __init__(self, logger=None, debug=False, lextab='sk_scan_tab'):
        super(skScanner, self).__init__()

        if not logger:
            logger = logging.getLogger('sk.lexer')
        self.logger = logger
        self._debug = debug
        self._lextab = lextab

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
    def input(self, buf):
        return self.lexer.input(buf)


    def tokenize(self, buf, startline=1):
        # Reset lexer state
        self.reset(lineno=startline)

        self.lexer.input(buf)
        res = []
        while True:
            try:
                tok = self.lexer.token()
                if not tok:
                    break
                res.append(tok)

            except lex.LexError as e:
                break

        return (self.errors, res, self.errinfo)


    def scan_skbuf(self, buf):

        (hdrbuf, prmbuf, cmdbuf, startline) = sk_common.get_skparts(buf)

        (errors, tokens, errinfo) = self.tokenize(cmdbuf,
                                                  startline=startline)

        if errors > 0:
            for errbnch in errinfo:
                errbnch.verbose = sk_common.mk_error(cmdbuf, errbnch, 10)

        res = Bunch.Bunch(tokens=tokens, errors=errors, errinfo=errinfo)
        return res


    def scan_skfile(self, skpath):

        with open(skpath, 'r') as in_f:
            buf = in_f.read()

        res = self.scan_skbuf(buf)
        res.filepath = skpath

        return res
