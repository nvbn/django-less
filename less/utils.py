from less.settings import LESS_EXECUTABLE, LESS_OUTPUT_DIR, LESS_STORE_IN_MEDIA
from django.conf import settings
import logging
import posixpath
import re
import os
import subprocess


logger = logging.getLogger("less")


STATIC_ROOT = getattr(settings, "STATIC_ROOT", getattr(settings, "MEDIA_ROOT"))
STATIC_URL = getattr(settings, "STATIC_URL", getattr(settings, "MEDIA_URL"))
MEDIA_ROOT = getattr(settings, "MEDIA_ROOT", None)
MEDIA_URL = getattr(settings, "MEDIA_URL", None)

class URLConverter(object):

    URL_PATTERN = re.compile(r'url\(([^\)]+)\)')

    def __init__(self, content, source_path):
        self.content = content
        self.source_dir = os.path.dirname(source_path)

    def convert_url(self, matchobj):
        url = matchobj.group(1)
        url = url.strip(' \'"')
        if url.startswith(('http://', 'https://', '/', 'data:')):
            return "url('%s')" % url
        full_url = posixpath.normpath("/".join([self.source_dir, url]))
        return "url('%s')" % full_url

    def convert(self):
        return self.URL_PATTERN.sub(self.convert_url, self.content.decode('utf8'))


def compile_less(input, output, less_path):
    if LESS_STORE_IN_MEDIA:
        less_root = os.path.join(MEDIA_ROOT, LESS_OUTPUT_DIR)
    else:
        less_root = os.path.join(STATIC_ROOT, LESS_OUTPUT_DIR)

    if not os.path.exists(less_root):
        os.makedirs(less_root)

    args = [LESS_EXECUTABLE, input]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, errors = p.communicate()

    if errors:
        logger.error(errors)
        return False

    output_directory = os.path.dirname(output)
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    compiled_file = open(output, "w+")
    compiled_css = URLConverter(out, os.path.join(STATIC_URL, less_path)).convert()
    compiled_file.write(compiled_css.encode('utf8'))
    compiled_file.close()

    return True


class MtimeChecker(object):
    def __init__(self):
        self._file_mtime = {}

    def check(self, name, mtime):
        return self._file_mtime.get(name) == mtime

    def set(self, name, mtime):
        self._file_mtime[name] = mtime


mtime_checker = MtimeChecker()
