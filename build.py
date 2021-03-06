#!/usr/bin/env python

from __future__ import unicode_literals
import sys
import os
import re
import json
from io import open
from sys import argv
from glob import glob
from copy import deepcopy
from datetime import datetime
from collections import OrderedDict
from shutil import rmtree, copy

sys.dont_write_bytecode = True
# Makes it runnable from any directory
os.chdir(os.path.split(os.path.abspath(__file__))[0])

pj = os.path.join

src_dir = os.path.abspath('src')
build_dir = os.path.abspath('build')
platform_dir = os.path.abspath('platform')
l10n_dir = os.path.abspath('l10n')


if not os.path.isdir(src_dir) or not os.path.isdir(platform_dir):
    raise SystemExit('src or platform directory not found')

if not os.path.isdir(build_dir):
    os.makedirs(build_dir)


locale_list = None
languages = OrderedDict({})
l10n_strings_sparse = OrderedDict({})
l10n_strings_full = OrderedDict({})
app_desc_string = 'appDescriptionShort'

common_app_code = None
platforms = []
params = {
    '-meta': False,
    '-pack': False,
    '-useln': False
}

def add_platform(platform):
    if os.path.exists(pj(platform_dir, platform, 'build.py')):
        platforms.append(platform)
        return True

    return False


for i in range(1, len(argv)):
    arg = argv[i];

    if arg in params:
        params[arg] = True
    elif not add_platform(arg):
        sys.stderr.write('Invalid argument: ' + arg + '\n')

if params['-useln'] and params['-pack']:
    params['-useln'] = False


if len(platforms) == 0:
    for f in os.listdir(platform_dir):
        if os.path.isdir(pj(platform_dir, f)):
            add_platform(f)


if len(platforms) == 0:
    raise SystemExit('No platforms were found.')


with open(os.path.abspath('config.json'), encoding='utf-8') as f:
    config = json.load(f)

if not config:
    raise SystemExit('Config file failed to load!')


def_lang = config['def_lang']
config['version'] = re.sub(
    '(?<=\.)0+',
    '',
    datetime.utcnow().strftime("%Y.%m%d.%H%M")
)

def read_locales(locale_glob, exclude=None):
    global locale_list, languages, l10n_strings_sparse
    mandatory_locale_groups = ['options']

    if locale_list is None:
        locale_names_path = pj(l10n_dir, 'locale_names.json')

        with open(locale_names_path, encoding='utf-8') as f:
            locale_list = json.load(f)

    locale_glob = pj(l10n_dir, 'locales', locale_glob + '.json')

    for locale_file_name in glob(locale_glob):
        alpha2 = os.path.basename(locale_file_name).replace('.json', '')

        if alpha2 not in locale_list:
            continue

        if exclude and alpha2 in exclude:
            continue

        with open(locale_file_name, encoding='utf-8') as f:
            locale = json.load(f, object_pairs_hook=OrderedDict)

        if not locale:
            continue

        translators = locale['_translators']
        del locale['_translators']

        locale_name = locale_list[alpha2]
        languages[alpha2] = {
            'name': ('{} [{}]' if 'native' in locale_name else '{}').format(
                locale_name['english'],
                locale_name['native'] if 'native' in locale_name else ''
            ),
            'translators': translators
        }

        groups = OrderedDict({})
        l10n_strings_sparse[alpha2] = groups

        for grp in locale:
            is_def = alpha2 == def_lang

            if not is_def and grp not in l10n_strings_sparse[def_lang]:
                continue

            # Ignore group description
            if '?' in locale[grp]:
                del locale[grp]['?']

            groups[grp] = OrderedDict({})

            if not is_def:
                def_strings = l10n_strings_sparse[def_lang][grp]

            for string in locale[grp]:
                # Ignore redundant strings
                if not is_def:
                    if string not in def_strings:
                        continue

                    if locale[grp][string]['>'] == def_strings[string]:
                        continue

                groups[grp][string] = locale[grp][string]['>']

            if len(groups[grp]) == 0:
                del groups[grp]

        if len(groups) == 0:
            del languages[alpha2]
            del l10n_strings_sparse[alpha2]
            continue

        # Add groups if they're missing
        for grp in mandatory_locale_groups:
            if grp not in groups:
                groups[grp] = OrderedDict({})

        if 'groupless' in groups:
            grp = groups['groupless']
        else:
            grp = {}

        if app_desc_string not in grp:
            grp = languages[def_lang]

            if app_desc_string not in grp:
                grp = None
                languages[alpha2][app_desc_string] = app_desc_string

        if grp:
            languages[alpha2][app_desc_string] = grp[app_desc_string]


# Some platforms are able to use strings from the default locale.
# Some not, and this fills their missing strings from the default language.
def add_missing_strings():
    def_strings = l10n_strings_sparse[def_lang]

    for alpha2 in l10n_strings_sparse:
        l10n_strings_full[alpha2] = OrderedDict({})

        if alpha2 == def_lang:
            l10n_strings_full[alpha2] = def_strings
            continue

        locale_strings = l10n_strings_sparse[alpha2]

        for grp in def_strings:
            filled_grp = OrderedDict({})
            defaults_used = False

            for string in def_strings[grp]:
                if string in locale_strings[grp]:
                    filled_grp[string] = locale_strings[grp][string]
                else:
                    defaults_used = True
                    filled_grp[string] = def_strings[grp][string]

            if defaults_used:
                l10n_strings_full[alpha2][grp] = filled_grp
            else:
                l10n_strings_full[alpha2][grp] = locale_strings[grp]


read_locales(def_lang)


if def_lang not in languages:
    raise SystemExit('Default language not found!')


read_locales('*', [def_lang])


for alpha2 in l10n_strings_sparse:
    if 'groupless' in l10n_strings_sparse[alpha2]:
        del l10n_strings_sparse[alpha2]['groupless']


locales_json = os.path.abspath(pj('build', 'locales.json'))

with open(locales_json, 'wt', encoding='utf-8', newline='\n') as f:
    locales = {}

    for alpha2 in languages:
        language = languages[alpha2]

        locales[alpha2] = {
            'name': language['name']
        }

        if not language['translators']:
            continue

        locales[alpha2]['translators'] = deepcopy(language['translators'])

        for i, translator in enumerate(language['translators']):
            if 'realname' in translator and 'name' in translator:
                translator['realname'] = '({})'.format(translator['realname'])

            if 'web' in translator:
                translator['web'] = '[{}]'.format(translator['web'])
            elif 'email' in translator:
                translator['web'] = '<{}>'.format(translator['email'])
                del translator['email']

            language['translators'][i] = ' '.join(translator.values())

        language['translators'] = ', '.join(language['translators'])

    locales['_'] = def_lang

    f.write(
        json.dumps(
            locales,
            separators=(',', ':'),
            sort_keys=True,
            ensure_ascii=False
        )
    )


def copytree(src, dst, symlinks=False):
    try:
        os.makedirs(dst)
    except:
        pass

    for name in os.listdir(src):
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)

        if os.path.isdir(srcname):
            copytree(srcname, dstname, symlinks)
        elif symlinks:
            os.symlink(srcname, dstname)
        else:
            copy(srcname, dstname)


for platform_name in platforms:
    try:
        open(pj(platform_dir, '__init__.py'), 'a').close()
        open(pj(platform_dir, platform_name, '__init__.py'), 'a').close()
        platform = __import__(
            'platform.' + platform_name + '.build',
            fromlist=['build']
        )
    finally:
        os.remove(pj(platform_dir, '__init__.py'))
        os.remove(pj(platform_dir, platform_name, '__init__.py'))


    platform = platform.Platform(
        build_dir,
        config,
        languages,
        app_desc_string,
        os.path.abspath(pj(
            build_dir,
            config['name'].lower() + '-' + config['version']
        ))
    )


    if not params['-meta']:
        try:
            rmtree(platform.build_dir)
        except:
            pass

    try:
        os.makedirs(platform.build_dir)
    except:
        pass

    if not os.path.exists(platform.build_dir):
        sys.stderr.write(
            'Failed to create platform directory for ' + platform_name + '\n'
        )
        del platform
        continue

    platform.write_manifest()

    locale_dir = pj(platform.build_dir, platform.l10n_dir)

    if os.path.exists(locale_dir):
        try:
            rmtree(locale_dir)
        except:
            pass

    try:
        os.makedirs(locale_dir)
    except:
        sys.stderr.write(
            'Failed to create locales directory for ' + platform_name + '\n'
        )
        del platform
        continue

    if platform.requires_all_strings:
        if len(l10n_strings_full) == 0:
            add_missing_strings()

        platform.write_locales(l10n_strings_full)
    else:
        platform.write_locales(l10n_strings_sparse)

    copy(locales_json, platform.build_dir)

    if not params['-meta']:
        copytree(
            src_dir,
            platform.build_dir,
            params['-useln']
        )

        platform_js_dir = pj(platform_dir, platform_name, 'js')

        if params['-useln']:
            os.symlink(
                pj(platform_js_dir, 'app_bg.js'),
                pj(platform.build_dir, 'js', 'app_bg.js')
            )
        else:
            copy(
                pj(platform_js_dir, 'app_bg.js'),
                pj(platform.build_dir, 'js')
            )

        # app.js is extended with app_common.js, so symlink is not applicable
        copy(pj(platform_js_dir, 'app.js'), pj(platform.build_dir, 'includes'))


        if common_app_code is None:
            f_path = pj(platform_dir, 'app_common.js')

            with open(f_path, 'rt', encoding='utf-8', newline='\n') as f:
                common_app_code = f.read()

        f_path = pj(platform.build_dir, 'includes', 'app.js')

        with open(f_path, 'at', encoding='utf-8', newline='\n') as f:
            f.write(common_app_code)

        platform.write_files(params['-useln'])

        if params['-pack']:
            platform.write_package()
            platform.write_update_file()
            print('Package is ready for ' + platform_name +
                ' @ ' + platform.build_dir)
        else:
            print('Files are ready for ' + platform_name +
                ' @ ' + platform.build_dir)
    else:
        if params['-pack']:
            platform.write_update_file()

        print('Meta-data has been generated for ' + platform_name)

    del platform


if os.path.isfile(locales_json):
    os.remove(locales_json)

