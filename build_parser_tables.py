#!/usr/bin/env python3
#
# build_parser_tables -- build the parser tables
#
import sys
import logging
logger = logging.getLogger('build_parser_tables')

from oscript.parse import (sk_lexer, param_parser, sk_parser,
                           para_lexer, para_parser)

# build param parser state machine table
lex = sk_lexer.skScanner(logger=logger, lextab='scan1_tab', debug=False)
pp = param_parser.paramParser(lex, logger=logger)
pp.build()

# build OPE parser state machine table
lex = sk_lexer.skScanner(logger=logger, lextab='scan2_tab', debug=False)
op = sk_parser.opeParser(lex, logger=logger)
op.build()

# build skeleton parser state machine table
lex = sk_lexer.skScanner(logger=logger, lextab='scan3_tab', debug=False)
sp = sk_parser.skParser(lex, logger=logger)
sp.build()

# build PARA parser state machine table
lex = para_lexer.paraScanner(logger=logger, debug=False)
pp2 = para_parser.paraParser(lex, logger=logger)
# not currently necessary for this parser, builds in constructor
#pp2.build()
