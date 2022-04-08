
degPerHMSHour = 15.0      #360/24
degPerHMSMin  = 0.25      #360.0/24/60
degPerHMSSec  = 1.0/240.0 #360.0/24/60/60

degPerDmsMin  = 1.0/60.0
degPerDmsSec  = 1.0/3600.0

HMSHourPerDeg = 1.0/15.0
HMSMinPerDeg  = 4.0
HMSSecPerDeg  = 240.0


def parseHMS(ra_in):
    """   input HHMMSS.sss '''
       Decode an absolute RA value in 'funky SOSS format' (see convertToFloat()),
       and return a tuple containing hours, minutes and
       seconds of RA."""
    # make sure that the (offset_)dec/(offset_)ra is numeric
    ra_in = float(ra_in)
    # then convert it into the formatted string
    input_str  = '%010.3f' % (ra_in)

    # break down the parts
    return (int  (input_str[0:2]),
            int  (input_str[2:4]),
            float(input_str[4:]))

def parseDMS(dec_in):
    """Decode an angular value in 'funky SOSS format' (see convertToFloat()),
       and return a tuple containing sign (+1 or -1), degrees, minutes and
       seconds of arc."""

    # make sure that the input value is numeric
    dec_in = float(dec_in)

    # then convert it into the formatted string
    input_str  = '%+011.3f' % (dec_in)

    # break down the parts
    if input_str[0] == '-':
        input_sign = -1
    else:
        input_sign = 1

    return (input_sign,
            int  (input_str[1:3]),
            int  (input_str[3:5]),
            float(input_str[5:]))

def hmsToHour(s, h, m, sec):
    """Convert signed RA/HA hours, minutes, seconds to floating point hours."""
    return s * (h + m/60.0 + sec/3600.0)

def hmsToDeg(h, m, s):
    """Convert RA hours, minutes, seconds into an angle in degrees."""
    return h * degPerHMSHour + m * degPerHMSMin + s * degPerHMSSec

def dmsToDeg(sign, deg, min, sec):
    """Convert dec sign, degrees, minutes, seconds into a signed angle in degrees."""
    return sign * (deg + min * degPerDmsMin + sec * degPerDmsSec)

def funkyHMStoDeg(HMS):
    (hrs, min, sec) = parseHMS(HMS)
    return hmsToDeg(hrs, min, sec)

def funkyDMStoDeg(DMS):
    """Convert funky DMS format, possibly signed, into degrees.
       Both input (DMS) and return values are floating point."""
    s, h, m, sec = parseDMS(DMS)
    return hmsToHour(s, h, m, sec)
