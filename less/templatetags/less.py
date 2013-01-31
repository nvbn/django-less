from tempfile import NamedTemporaryFile
from ..cache import get_cache_key, get_hexdigest, get_hashed_mtime
from ..utils import compile_less, STATIC_ROOT, MEDIA_ROOT, mtime_checker
from ..settings import (
    LESS_EXECUTABLE, LESS_USE_CACHE,
    LESS_CACHE_TIMEOUT, LESS_OUTPUT_DIR, 
    LESS_DEVMODE, LESS_DEVMODE_WATCH_DIRS,
    LESS_STORE_IN_MEDIA,
)
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.template.base import Library, Node, TemplateSyntaxError
import logging
import subprocess
import os
import sys
import re


logger = logging.getLogger("less")


register = Library()


class InlineLessNode(Node):

    def __init__(self, nodelist):
        self.nodelist = nodelist

    def compile(self, source):
        source_file = NamedTemporaryFile(delete=False)
        source_file.write(source)
        source_file.close()
        args = [LESS_EXECUTABLE, source_file.name]

        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, errors = p.communicate()
        os.remove(source_file.name)
        if out:
            return out.decode("utf-8")
        elif errors:
            return errors.decode("utf-8")

        return u""

    def render(self, context):
        output = self.nodelist.render(context)

        if LESS_USE_CACHE:
            cache_key = get_cache_key(get_hexdigest(output))
            cached = cache.get(cache_key, None)
            if cached is not None:
                return cached
            output = self.compile(output)
            cache.set(cache_key, output, LESS_CACHE_TIMEOUT)
            return output
        else:
            return self.compile(output)


@register.tag(name="inlineless")
def do_inlineless(parser, token):
    nodelist = parser.parse(("endinlineless",))
    parser.delete_first_token()
    return InlineLessNode(nodelist)


def less_paths(path):
    if LESS_STORE_IN_MEDIA:
        full_path = os.path.join(settings.EDITABLE_STATIC_PATH, path)
        output_part = os.path.join(MEDIA_ROOT, LESS_OUTPUT_DIR)
    else:
        full_path = os.path.join(STATIC_ROOT, path)
        output_part = os.path.join(STATIC_ROOT, LESS_OUTPUT_DIR)

    if settings.DEBUG and not os.path.exists(full_path):
        # while developing it is more confortable
        # searching for the less files rather then
        # doing collectstatics all the time
        full_path = finders.find(path)

        if full_path is None:
            raise TemplateSyntaxError("Can't find staticfile named: {}".format(path))

    file_name = os.path.split(path)[-1]
    output_dir = os.path.join(output_part, os.path.dirname(path))

    return full_path, file_name, output_dir


LESS_IMPORT_RE = re.compile(r"""@import\s+['"](.+?\.less)['"]\s*;""")


def _get_imports(path):
    paths = []
    root = os.path.dirname(path)
    with open(path) as less_file:
        for line in less_file.readlines():
            for imported in LESS_IMPORT_RE.findall(line):
                paths.append(os.path.join(root, imported))
    return paths


def _check_mtimes(paths):
    result = True
    for path in paths:
        mtime = get_hashed_mtime(path)
        if not mtime_checker.check(path, mtime):
            result = False
            mtime_checker.set(path, mtime)
    return result


@register.simple_tag
def less(path):
    logger.info("processing file %s" % path)

    full_path, file_name, output_dir = less_paths(path)
    print full_path
    base_file_name = os.path.splitext(file_name)[0]

    hashed_mtime = get_hashed_mtime(full_path)
    output_file = "%s-%s.css" % (base_file_name, hashed_mtime)
    output_path = os.path.join(output_dir, output_file)

    encoded_full_path = full_path

    if isinstance(full_path, unicode):
        filesystem_encoding = sys.getfilesystemencoding() or sys.getdefaultencoding()
        encoded_full_path = full_path.encode(filesystem_encoding)

    imports = _get_imports(full_path)

    if not os.path.exists(output_path) or not _check_mtimes(imports):
        if not compile_less(encoded_full_path, output_path, path):
            return path

        # Remove old files
        compiled_filename = os.path.split(output_path)[-1]
        for filename in os.listdir(output_dir):
            if filename.startswith(base_file_name) and filename != compiled_filename:
                os.remove(os.path.join(output_dir, filename))
    return os.path.join(LESS_OUTPUT_DIR, os.path.dirname(path), output_file)
