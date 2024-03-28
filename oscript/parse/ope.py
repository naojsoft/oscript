#
# ope.py -- helper code for processing legacy OPE (observation) files
#
import re, sys, os
import functools

from g2base import Bunch


class OPEerror(Exception):
    pass


# OPE file regexes
# old style
ope_regex1 = re.compile(r'^.*\<HEADER\>(?P<hdr>.*)\</HEADER\>\s*'
'\<PARAMETER_LIST\>(?P<params>.*)\</PARAMETER_LIST\>\s*'
'\<COMMAND\>\s*(?P<cmd>.+)\s*\</COMMAND\>\s*$',
re.MULTILINE | re.DOTALL | re.IGNORECASE)
# new style
ope_regex2 = re.compile(r'^.*\:HEADER\s+(?P<hdr>.*)'
'\:PARAMETER(_LIST)?\s+(?P<params>.*)'
'\:COMMAND\s+(?P<cmd>.+)\s*$',
re.MULTILINE | re.DOTALL | re.IGNORECASE)

# CD file regex
# old style
cd_regex1 = re.compile(r'^.*\<COMMAND\>\s*(?P<cmd>.+)\s*\</COMMAND\>\s*$',
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)
# new style
cd_regex2 = re.compile(r'^.*\:COMMAND\s+(?P<cmd>.+)\s*$',
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)

# PRM includes regex
load_regex = re.compile(r'^\*LOAD\s*"(.+)"\s*$', re.IGNORECASE)

# regex for matching variable references
regex_varref = re.compile(r'^(.*?)(\$[\w_\.]+)(.*)$')

# regexes for checking RA and DEC in OPE files
regex_ra1 = re.compile(r'^.*[\s=]RA=([\d\.]+)(.*)$', re.IGNORECASE)
regex_ra2 = re.compile(r'^(?P<hr>\d\d)(?P<min>\d\d)(?P<sec>\d\d\.\d\d?\d?)$')
regex_dec1 = re.compile(r'^.*[\s=]DEC=([\d\+\-\.]+)(.*)$', re.IGNORECASE)
regex_dec2 = re.compile(r'^(?P<deg>[\-\+]?\d\d)(?P<min>\d\d)(?P<sec>\d\d\.\d\d?\d?)$')

def toupper(cmdstr):
    # TODO: is there a C-based module for something like this available?
    # This is terribly inefficient
    quotes = ('"', "'")

    start_quote = None
    chars = []             # Character buffer

    charlst = list(cmdstr)

    while len(charlst) > 0:
        c = charlst.pop(0)

        # process double quotes
        if c in quotes:
            # if we are not building a quoted string, then turn on quote
            # flag and continue scanning
            if not start_quote:
                start_quote = c
                chars.append(c)
                continue
            elif start_quote != c:
                chars.append(c)
                continue
            else:
                # end of quoted string
                chars.append(c)
                start_quote = None
                continue
        else:
            if start_quote != None:
                chars.append(c)
            else:
                chars.append(c.upper())

    return ''.join(chars)


def locate_prm(filename, include_dirs):
    """Function to locate a filename within a list of directories.
    Returns the first valid path found.
    """

    for dirpath in include_dirs:
        path = os.path.join(dirpath, filename)
        if os.path.exists(path):
            return path

    raise OPEerror("Could not locate included PRM file '%s' in %s" % (
        filename, str(include_dirs)))


def prepend_prm(lines, filename, include_dirs, prm_errmsg_list):

    try:
        filepath = locate_prm(filename, include_dirs)
    except OPEerror as e:
        errmsg = str(e)
        prm_errmsg_list.append(errmsg)
        return

    try:
        with open(filepath, 'r') as in_f:
            buf = in_f.read()

        # Prepend the lines to the current set of lines
        # TODO: there has got to be a more efficient way
        # to do this
        newlines = buf.split('\n')
        newlines.reverse()
        for line in newlines:
            lines.insert(0, line)

    except IOError as e:
        raise OPEerror(str(e))


def get_sections(opebuf):
    def process_match(match):
        hdrbuf = match.group('hdr').strip()
        prmbuf = match.group('params').strip().replace('\t', ' ')
        cmdbuf = match.group('cmd').strip()

        return (hdrbuf, prmbuf, cmdbuf)

    for regex in (ope_regex1, ope_regex2):
        match = regex.match(opebuf)
        if match:
            return process_match(match)

    for regex in (cd_regex1, cd_regex2):
        match = regex.match(opebuf)
        if match:
            header = ''
            plist = ''
            cmds = match.group('cmd')
            return (header, plist, cmds)

    raise OPEerror("String contents do not match expected format")


def get_vars(plist, include_dirs):
    """Build substitution dictionary from the <Parameter_List> section
    of an OPE file."""

    prm_errmsg_list = []
    lines = plist.split('\n')
    substDict = Bunch.caselessDict()
    while len(lines) > 0:
        line = lines.pop(0)
        line = line.strip()
        match = load_regex.match(line)
        if match:
            try:
                prepend_prm(lines, match.group(1), include_dirs, prm_errmsg_list)
            except IOError as e:
               errmsg = str(e)
               prm_errmsg_list.append(errmsg)
            continue

        # convert to uc
        line = toupper(line)

        if line.startswith('#') or line.startswith('*') or (len(line) == 0):
            continue

        if '=' in line:
            idx = line.find('=')
            var = line[0:idx].strip()
            val = line[idx+1:].strip()
            substDict[var] = val

    return Bunch.Bunch(varDict=substDict, prm_errmsg_list=prm_errmsg_list)


def get_vars_ope(opebuf, include_dirs):
    """Build substitution dictionary from the <Parameter_List> section
    of an OPE file."""
    (header, plist, cmds) = get_sections(opebuf)
    return get_vars(plist, include_dirs)

def check_ra(ra):
    match = regex_ra2.match(ra)
    if not match:
        raise OPEerror("RA of '%s' does not appear to be formatted correctly" % (
            ra))

    try:
        hr = int(match.group('hr'))
        assert((hr >= 0) and (hr <= 23)), OPEerror("Bad hour: %d" % (hr))
        mn = int(match.group('min'))
        assert((mn >= 0) and (mn < 60)), OPEerror("Bad minutes: %d" % (mn))
        sec = float(match.group('sec'))
        assert((sec >= 0) and (sec < 60)), OPEerror("Bad seconds: %d" % (sec))
    except Exception as e:
        raise OPEerror("RA of '%s' appears to have incorrect values: %s" % (
            ra, str(e)))

    return (hr, mn, sec)

def check_dec(dec):
    match = regex_dec2.match(dec)
    if not match:
        raise OPEerror("DEC of '%s' does not appear to be formatted correctly" % (dec))

    try:
        deg = int(match.group('deg'))
        assert((deg >= -90) and (deg <= 90)), OPEerror("Bad degrees: %d" % (deg))
        mn = int(match.group('min'))
        assert((mn >= 0) and (mn < 60)), OPEerror("Bad minutes: %d" % (mn))
        sec = float(match.group('sec'))
        assert((sec >= 0) and (sec < 60)), OPEerror("Bad seconds: %d" % (sec))
    except Exception as e:
        raise OPEerror("DEC of '%s' appears to have incorrect values: %s" % (
            dec, str(e)))

    return (deg, mn, sec)

def check_coords(line):
    # Check line for RA's
    match = regex_ra1.match(line)
    while match:
        ra = match.group(1)
        check_ra(ra)
        sfx = match.group(2)
        if (len(sfx) > 0) and (not sfx.startswith(' ')):
            raise OPEerror("No space between RA and next parameter")
        match = regex_ra1.match(sfx)

    # Check line for DEC's
    match = regex_dec1.match(line)
    while match:
        dec = match.group(1)
        check_dec(dec)
        sfx = match.group(2)
        if (len(sfx) > 0) and (not sfx.startswith(' ')):
            raise OPEerror("No space between DEC and next parameter")
        match = regex_dec1.match(sfx)


def get_coords(line):
    match1 = regex_ra1.match(line)
    match2 = regex_dec1.match(line)

    if not match1 or not match2:
        return None

    ra = match1.group(1)
    ra_info = check_ra(ra)

    dec = match2.group(1)
    dec_info = check_dec(dec)

    return (ra_info, dec_info)

def check_ope(buf, include_dirs=None):
    """
    Parse an OPE file and return a Bunch of information about it.
    Returns a bunch with several items defined:
      reflist: a list of all variable references (each is a bunch)
      refset: a set of all variable references (just variable names)
      badlist: a list of all undefined variable references (each is a bunch)
      badset: a set of all undefined variable references (just variable names)
      taglist: a list of all tag lines encountered (each is a bunch)
    """
    if include_dirs == None:
        include_dirs = []

    # compute the variable dictionary
    vars_res = get_vars_ope(buf, include_dirs)

    refset = set([])
    badset = set([])
    reflist = []
    badlist = []
    taglist = []
    badcoords = []

    def addvarrefs(lineno, line):
        offset = 0
        match = regex_varref.match(line)
        while match:
            pfx, varref, sfx = match.groups()
            #print "1) %d pfx=(%s) varref=(%s) sfx=(%s)" % (
            #    lineno, pfx, varref, sfx)
            offset += len(pfx)
            start = offset
            offset += len(varref)
            end = offset
            varref = varref.upper()[1:]

            refset.add(varref)
            bnch = Bunch.Bunch(varref=varref, lineno=lineno,
                               text=line,
                               start=start, end=end)
            reflist.append(bnch)

            try:
                res = vars_res.varDict[varref]
            except KeyError:
                badset.add(varref)
                badlist.append(bnch)

            match = regex_varref.match(sfx)

    lineno = 0
    for line in buf.split('\n'):
        lineno += 1
        sline = line.strip()
        if sline.startswith('###'):
            taglist.append(Bunch.Bunch(lineno=lineno,
                                       text=line,
                                       tags=['comment3']))

        elif sline.startswith('##'):
            taglist.append(Bunch.Bunch(lineno=lineno,
                                       text=line,
                                       tags=['comment2']))

        elif sline.startswith('#'):
            taglist.append(Bunch.Bunch(lineno=lineno,
                                       text=line,
                                       tags=['comment1']))

        else:
            try:
                check_coords(line)

            except OPEerror as e:
                bnch = Bunch.Bunch(errstr=str(e), lineno=lineno,
                                   text=line)
                badcoords.append(bnch)
            addvarrefs(lineno, line)


    return Bunch.Bunch(refset=refset, reflist=reflist,
                       badset=badset, badlist=badlist,
                       taglist=taglist, vardict=vars_res.varDict,
                       badcoords=badcoords,
                       prm_errmsg_list=vars_res.prm_errmsg_list)


def substitute_params(plist, cmdstr, include_dirs):

    vars_res = get_vars(plist, include_dirs)
    substDict = vars_res.varDict

    cmdstr = toupper(cmdstr)

    # Now substitute into the command line wherever we see any of these
    # varrefs

    # Sort vars so that longest ones are tried first
    vars = list(substDict.keys())
    key = functools.cmp_to_key(lambda x, y: len(y) - len(x))
    vars.sort(key=key)

    for key in vars:
        varref = '$%s' % key
        if varref in cmdstr:
            cmdstr = cmdstr.replace(varref, substDict[key])

    # Final sanity check
    # TODO: parse this with the OPE parser
    i = cmdstr.find('$')
    if i > 0:
        raise OPEerror("Not all variable references were converted: %s" % (
            cmdstr[i:]))

    return cmdstr


def getCmd(opebuf, cmdstr, include_dirs):

    try:
        (header, plist, cmds) = get_sections(opebuf)

        cmdstr = cmdstr.strip()

        #print "PLIST", plist
        #print "CMDSTR", cmdstr

        # Substitute parameters into command list
        #print "SUBST <== (%s) : %s" % (str(plist), cmdstr)
        cmdstr = substitute_params(plist, cmdstr, include_dirs)
        #print "SUBST ==> %s" % (cmdstr)

        return cmdstr

    except Exception as e:
        raise OPEerror("Can't extract command: %s" % str(e))


def get_targets(ope_buf, prm_dirs):

    re_obj = re.compile(r'^.*OBJECT=([\w\d_]+)(.*)$', re.IGNORECASE)
    # OBJECT names encased in double quotes
    re_obj2 = re.compile(r'^.*OBJECT=\"([^\"]+)\"(.*)$', re.IGNORECASE)
    re_eqx = re.compile(r'^.*\s+EQUINOX=\"?([\d\.]+)\"?(.*)$', re.IGNORECASE)
    re_ra = re.compile(r'^.*\s+RA=([\d\.]+)(.*)$', re.IGNORECASE)
    re_dec = re.compile(r'^.*\s+DEC=([\d\+\-\.]+)(.*)$', re.IGNORECASE)

    vars_res = get_vars_ope(ope_buf, prm_dirs)
    tgt_list = []

    for key, line in vars_res.varDict.items():
        m_obj = re_obj2.match(line)
        if m_obj is None:
            m_obj = re_obj.match(line)
        if m_obj is not None:
            tgtname = key
            objname = m_obj.group(1)
            m_ra = re_ra.match(line)
            m_dec = re_dec.match(line)
            m_eqx = re_eqx.match(line)
            if m_ra is not None and m_dec is not None:
                ra = m_ra.group(1)
                dec = m_dec.group(1)
                if m_eqx is None:
                    eq = "2000"
                else:
                    eq = m_eqx.group(1)

                tgt_list.append((tgtname, objname, ra, dec, eq))

    return Bunch.Bunch(tgt_list=tgt_list, prm_errmsg_list=vars_res.prm_errmsg_list)
