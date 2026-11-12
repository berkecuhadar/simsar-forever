"""YAML reading and writing.

ruamel.yaml in pure-Python mode, so installing never needs a C compiler. PyYAML had no Windows
wheels for Python 3.15 when that version came out, which broke installs on new Pythons.
"""

import io

from ruamel.yaml import YAML


def _yaml():
    y = YAML(typ="safe", pure=True)
    y.default_flow_style = False
    y.allow_unicode = True
    y.sort_base_mapping_type_on_output = False   # keep config sections in the order they were written
    return y


def load(stream):
    """Parse YAML from a string or an open text file. Empty input gives None."""
    return _yaml().load(stream)


def dump(data):
    out = io.StringIO()
    _yaml().dump(data, out)
    return out.getvalue()
