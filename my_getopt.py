#!/usr/bin/env python3
# -*- coding: utf8 -*-
# All strings are unicode (even docstrings)
from __future__ import unicode_literals

import sys
import getopt

def print_usage(cmd_name, options):
    """ Short usage output """
    usage_line = "Usage : %s" % (cmd_name)
    full_desc = ""
    for option in options:
        if option['optional']:
            usage_line += ' ['
        usage_line += ' -%s' % option['short']
        if option['arg']:
            if option['default']:
                usage_line += ' %s' % option['default']
            else:
                usage_line += ' <%s>' % option['name']
        if option['optional']:
            usage_line += ' ]'
            full_desc += "\t-{short}, --{long} : {desc}\n".format(**option)

    print(usage_line)
    print(full_desc)

def parse_opt(argv, options_def):
    """ Parse options passed to the script and return a dictionnary with the
    options value. """
    options = {}
    getopt_options = {
        'short' : "",
        'long' : []
    }

    for option in options_def:
        options[option['name']] = option['default']
        getopt_options['short'] += option['short']
        getopt_options['long'].append(option['long'])
        if option['arg']:
            getopt_options['short'] += ":"
            getopt_options['long'][-1] += "="

    try:
        opts, args = getopt.getopt(argv[1:], getopt_options['short'], getopt_options['long'])
    except getopt.GetoptError:
        sys.stderr.write('## ERROR ## Failed to parse options...\n')
        print_usage(argv[0], options_def)
        sys.exit(2)

    # There is some non-option arguments. Warn the user and continue
    if len(args) > 0:
        sys.stderr.write('## WARN  ## Some arguments are useless :\n')
        sys.stderr.write('%s\n' % (args))

    for opt, arg in opts:
        for option in options_def:
            if opt in ("-%s" % option['short'], "--%s" % option['long']):
                if option['arg']:
                    # Option with argument
                    options[option['name']] = arg
                else:
                    # Boolean option
                    options[option['name']] = True
                break

    if options['help']:
        print_usage(argv[0], options_def)
        exit(0)

    # Check that the mandatory option is not empty
    for option in options_def:
        if not option['optional'] and not options[option['name']]:
            sys.stderr.write('%s is a mandatory argument...\n\n' % option['name'])
            print_usage(argv[0], options_def)
            sys.exit(-1)

    return options

