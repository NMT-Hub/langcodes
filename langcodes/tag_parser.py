"""
This module implements a parser for language tags, according to the RFC 5646
(BCP 47) standard.

Here, we're only concerned with the syntax of the language tag. Looking up
what they actually mean in a data file is a separate step.

For a full description of the syntax of a language tag, see page 3 of
    http://tools.ietf.org/html/bcp47

>>> parse('en')
[('language', 'en')]

>>> parse('en_US')
[('language', 'en'), ('region', 'US')]

>>> parse('en-Latn')
[('language', 'en'), ('script', 'Latn')]

>>> parse('es-419')
[('language', 'es'), ('region', '419')]

>>> parse('zh-hant-tw')
[('language', 'zh'), ('script', 'Hant'), ('region', 'TW')]

>>> parse('zh-tw-hant')
Traceback (most recent call last):
    ...
langcodes.tag_parser.LanguageTagError: This script subtag, 'hant', is out of place. Expected variant, extension, or end of string.

>>> parse('de-DE-1901')
[('language', 'de'), ('region', 'DE'), ('variant', '1901')]

>>> parse('ja-latn-hepburn')
[('language', 'ja'), ('script', 'Latn'), ('variant', 'hepburn')]

>>> parse('ja-hepburn-latn')
Traceback (most recent call last):
    ...
langcodes.tag_parser.LanguageTagError: This script subtag, 'latn', is out of place. Expected variant, extension, or end of string.

>>> parse('zh-yue')
[('language', 'zh'), ('extlang', 'yue')]

>>> parse('zh-yue-Hant')
[('language', 'zh'), ('extlang', 'yue'), ('script', 'Hant')]

>>> parse('zh-min-nan')
[('grandfathered', 'zh-min-nan')]

>>> parse('x-dothraki')
[('language', 'x-dothraki')]

>>> parse('en-u-co-backwards-x-pig-latin')
[('language', 'en'), ('extension', 'u-co-backwards'), ('private', 'x-pig-latin')]

>>> parse('en-x-pig-latin-u-co-backwards')
[('language', 'en'), ('private', 'x-pig-latin-u-co-backwards')]

>>> parse('u-co-backwards')
Traceback (most recent call last):
    ...
langcodes.tag_parser.LanguageTagError: Expected a language code, got 'u'
"""
from __future__ import print_function, unicode_literals

# These tags should not be parsed by the usual parser; they're grandfathered
# in from RFC 3066. The 'irregular' ones don't fit the syntax at all; the
# 'regular' ones do, but would give meaningless results when parsed.
#
# These are all lowercased so they can be matched case-insensitively, as the
# standard requires.
EXCEPTIONS = {
    # Irregular exceptions
    "en-gb-oed", "i-ami", "i-bnn", "i-default", "i-enochian", "i-hak",
    "i-klingon", "i-lux", "i-mingo", "i-navajo", "i-pwn", "i-tao", "i-tay",
    "i-tsu", "sgn-be-fr", "sgn-be-nl", "sgn-ch-de",

    # Regular exceptions
    "art-lojban", "cel-gaulish", "no-bok", "no-nyn", "zh-guoyu", "zh-hakka",
    "zh-min", "zh-min-nan", "zh-xiang"
}

# Define the order of subtags as integer constants, but also give them names
# so we can describe them in error messages
EXTLANG, SCRIPT, REGION, VARIANT, EXTENSION = range(5)
SUBTAG_TYPES = ['extlang', 'script', 'region', 'variant', 'extension',
                'end of string']


def normalize_characters(tag):
    """
    BCP 47 is case-insensitive, and considers underscores equivalent to
    hyphens. So here we smash tags into lowercase with hyphens, so we can
    make exact comparisons.

    >>> normalize_characters('en_US')
    'en-us'
    >>> normalize_characters('zh-Hant_TW')
    'zh-hant-tw'
    """
    return tag.lower().replace('_', '-')


def parse(tag):
    """
    Parse the syntax of a language tag, without looking up anything in the
    registry, yet. Returns a list of (type, value) tuples indicating what
    information will need to be looked up.
    """
    tag = normalize_characters(tag)
    if tag in EXCEPTIONS:
        return [('grandfathered', tag)]
    else:
        # The first subtag is always either the language code, or 'x' to mark
        # the entire tag as private-use. Other subtags are distinguished
        # by their length and format, but the language code is distinguished
        # entirely by the fact that it is required to come first.
        subtags = tag.split('-')
        if subtags[0] == 'x':
            if len(subtags) == 1:
                raise LanguageTagError("'x' is not a language tag on its own")
            else:
                # the entire language tag is private use, but we know that,
                # whatever it is, it fills the "language" slot
                return [('language', tag)]
        elif len(subtags[0]) >= 2:
            return [('language', subtags[0])] + parse_subtags(subtags[1:])
        else:
            subtag_error(subtags[0], 'a language code')


def parse_subtags(subtags, expect=EXTLANG):
    """
    Parse everything that comes after the language tag: scripts, regions,
    variants, and assorted extensions.
    """
    # We parse the parts of a language code recursively: each step of
    # language code parsing handles one component of the code, recurses
    # to handle the rest of the code, and adds what it found onto the
    # list of things that were in the rest of the code.
    #
    # This could just as well have been iterative, but the loops would have
    # been convoluted.
    #
    # So here's the base case.
    if not subtags:
        return []

    # There's a subtag that comes next. We need to find out what it is.
    #
    # The primary thing that distinguishes different types of subtags is
    # length, but the subtags also come in a specified order. The 'expect'
    # parameter keeps track of where we are in that order. expect=REGION,
    # for example, means we're expecting a region code, or anything later
    # (because everything but the language is optional).
    subtag = subtags[0]
    tag_length = len(subtag)

    # In the usual case, our goal is to recognize what kind of tag this is,
    # and set it in 'tagtype' -- as an integer, so we can compare where it
    # should go in order. You can see the enumerated list of tagtypes above,
    # where the SUBTAG_TYPES global is defined.
    tagtype = None

    if tag_length == 0 or tag_length > 8:
        # Unless you're inside a private use tag or something -- in which case,
        # you're not in this function at the moment -- every component needs to
        # be between 1 and 8 characters.
        subtag_error(subtag, '1-8 characters')

    elif tag_length == 1:
        # A one-character subtag introduces an extension, which can itself have
        # sub-subtags, so we dispatch to a different function at this point.
        #
        # We don't need to check anything about the order, because extensions
        # necessarily come last.
        return parse_extension(subtags)

    elif tag_length == 2:
        if subtag.isalpha():
            # Two-letter alphabetic subtags are regions. These are the only
            # two-character subtags after the language.
            tagtype = REGION

    elif tag_length == 3:
        if subtag.isalpha():
            # Three-letter alphabetic subtags are 'extended languages'.
            # It's allowed for there to be up to three of them in a row, so we
            # need another function to enforce that. Before we dispatch to that
            # function, though, we need to check whether we're in the right
            # place in order.
            if expect <= EXTLANG:
                return parse_extlang(subtags)
            else:
                order_error(subtag, EXTLANG, expect)
        elif subtag.isdigit():
            # Three-digit subtags are broad regions, such as Latin America
            # (419).
            tagtype = REGION

    elif tag_length == 4:
        if subtag.isalpha():
            # Four-letter alphabetic subtags are scripts.
            tagtype = SCRIPT
        elif subtag[0].isdigit():
            # Four-character subtags that start with a digit are variants.
            tagtype = VARIANT

    else:
        # Tags of length 5-8 are variants.
        tagtype = VARIANT

    # That's the end of the big elif block for figuring out what kind of
    # subtag we have based on its length. Now we should do something with that
    # kind of subtag.

    if tagtype is None:
        # We haven't recognized a type of tag. This subtag just doesn't fit the
        # standard.
        subtag_error(subtag)

    elif tagtype < expect:
        # We got a tag type that was supposed to appear earlier in the order.
        order_error(subtag, tagtype, expect)

    else:
        # We've recognized a subtag of a particular type. If it's a region or
        # script, we expect the next subtag to be a strictly later type, because
        # there can be at most one region and one script. Otherwise, we expect
        # the next subtag to be the type we got or later.

        if tagtype in (SCRIPT, REGION):
            expect = tagtype + 1
        else:
            expect = tagtype

        # Get the name of this subtag type instead of its integer value.
        typename = SUBTAG_TYPES[tagtype]

        # Some subtags are conventionally written with capitalization. Apply
        # those conventions.
        if tagtype == SCRIPT:
            subtag = subtag.title()
        elif tagtype == REGION:
            subtag = subtag.upper()

        # Recurse on the remaining subtags.
        return [(typename, subtag)] + parse_subtags(subtags[1:], expect)


def parse_extlang(subtags):
    """
    Parse an 'extended language' tag, which consists of 1 to 3 three-letter
    language codes.

    Extended languages are used for distinguishing dialects/sublanguages
    (depending on your view) of macrolanguages such as Arabic, Bahasa Malay,
    and Chinese.

    It's supposed to also be acceptable to just use the sublanguage as the
    primary language code, and your code should know what's a macrolanguage of
    what. For example, 'zh-yue' and 'yue' are the same language (Cantonese),
    and differ only in whether they explicitly spell out that Cantonese is a
    kind of Chinese.
    """
    index = 0
    parsed = []
    while index < len(subtags) and len(subtags[index]) == 3 and index < 3:
        parsed.append(('extlang', subtags[index]))
        index += 1
    return parsed + parse_subtags(subtags[index:], SCRIPT)


def parse_extension(subtags):
    """
    An extension tag consists of a 'singleton' -- a one-character subtag --
    followed by other subtags. Extension tags are in the BCP 47 syntax, but
    their meaning is outside the scope of the standard.

    For example, there's the u- extension, which is used for setting Unicode
    properties in some context I'm not aware of.

    If the singleton is 'x', it's a private use extension, and consumes the
    rest of the tag. Otherwise, it stops at the next singleton.
    """
    subtag = subtags[0]
    if len(subtags) == 1:
        raise LanguageTagError(
            "The subtag %r must be followed by something" % subtag
        )

    if subtag == 'x':
        # Private use. Everything after this is arbitrary codes that we
        # can't look up.
        return [('private', '-'.join(subtags))]

    else:
        # Look for the next singleton, if there is one.
        boundary = 1
        while boundary < len(subtags) and len(subtags[boundary]) != 1:
            boundary += 1

        # We've parsed a complete extension subtag. Return to the main
        # parse_subtags function, but expect to find nothing but more
        # extensions at this point.
        return ([('extension', '-'.join(subtags[:boundary]))]
                + parse_subtags(subtags[boundary:], EXTENSION))


class LanguageTagError(ValueError):
    pass


def order_error(subtag, got, expected):
    """
    Output an error indicating that tags were out of order.
    """
    options = SUBTAG_TYPES[expected:]
    if len(options) == 1:
        expect_str = options[0]
    elif len(options) == 2:
        expect_str = '%s or %s' % (options[0], options[1])
    else:
        expect_str = '%s, or %s' % (', '.join(options[:-1]), options[-1])
    got_str = SUBTAG_TYPES[got]
    raise LanguageTagError("This %s subtag, %r, is out of place. "
                           "Expected %s." % (got_str, subtag, expect_str))


def subtag_error(subtag, expected='a valid subtag'):
    """
    Try to output a reasonably helpful error message based on our state of
    parsing. Most of this code is about how to list, in English, the kinds
    of things we were expecting to find.
    """
    raise LanguageTagError("Expected %s, got %r" % (expected, subtag))

