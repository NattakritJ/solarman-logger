from __future__ import annotations

import ast
import time
import yaml
import asyncio
import aiofiles

from functools import wraps
from logging import getLogger
from typing import Any, Iterable
from slugify import slugify as _slugify

from .const import *

_LOGGER = getLogger(__name__)

def retry(ignore: tuple = ()):
    def decorator(f):
        @wraps(f)
        async def wrapper(*args, **kwargs):
            try:
                return await f(*args, **kwargs)
            except ignore:
                raise
            except Exception:
                return await f(*args, **kwargs)
        return wrapper
    return decorator

def throttle(delay: float = 1):
    def decorator(f):
        l = [0]
        @wraps(f)
        async def wrapper(*args, **kwargs):
            if (d := delay - (time.time() - l[0])) > 0:
                await asyncio.sleep(d)
            l[0] = time.time()
            return await f(*args, **kwargs)
        return wrapper
    return decorator

def create_task(coro, *, name = None, context = None):
    return asyncio.get_running_loop().create_task(coro, name = name, context = context)

async def yaml_open(file):
    async with aiofiles.open(file) as f:
        return yaml.safe_load(await f.read())

def bulk_inherit(target: dict, source: dict, *keys: list):
    for k in source.keys() if len(keys) == 0 else source.keys() & keys:
        if not k in target and (v := source.get(k)) is not None:
            target[k] = v
    return target

def ensure_list(value):
    return value if isinstance(value, list) else [value]

def ensure_list_safe_len(value: list):
    return ensure_list(value), len(value) if isinstance(value, list) else (1 if isinstance(value, dict) and value else 0)

def create_request(code: int, start: int, end: int):
    return { REQUEST_CODE: code, REQUEST_START: start, REQUEST_END: end, REQUEST_COUNT: end - start + 1 }

def all_equals(values, value):
    return all(i == value for i in values)

def all_same(values):
    return all(i == values[0] for i in values)

def group_when(iterable, predicate):
    i, x, size = 0, 0, len(iterable)
    while i < size - 1:
        if predicate(iterable[i], iterable[i + 1], iterable[x]):
            yield iterable[x:i + 1]
            x = i + 1
        i += 1
    yield iterable[x:size]

def format(value: Any):
    return value if not isinstance(value, (bytes, bytearray)) else value.hex(" ")

def strepr(value: Any):
    return s if (s := str(value)) else repr(value)

def unwrap(source: dict, key: Any, mod: int = 0):
    if (c := source.get(key)) is not None and isinstance(c, list):
        source[key] = c[mod] if mod < len(c) else c[-1]
    return source

def slugify(*items: Iterable[str | None], separator: str = "_"):
    return _slugify(separator.join(filter(None, items)), separator = separator)

def entity_key(object: dict):
    return slugify(object["name"], object["platform"])

def enforce_parameters(source: dict, parameters: dict):
    return len((keys := source.keys() & parameters.keys())) == 0 or all(source[k] <= parameters[k] for k in keys)

def preprocess_descriptions(item, group, table, code, parameters):
    def modify(source: dict):
        for i in dict(source):
            if i in ("scale", "min", "max", "default", "step"):
                unwrap(source, i, parameters[CONF_MOD])
            if i == "registers" and source[i] and (isinstance(source[i], list) and isinstance(source[i][0], list)):
                unwrap(source, i, parameters[CONF_MOD])
                if not source[i]:
                    source["disabled"] = True
            elif isinstance(source[i], dict):
                modify(source[i])

    if not "platform" in item:
        item["platform"] = "sensor" if not "configurable" in item else "number"

    item["key"] = entity_key(item)

    modify(item)

    if (sensors := item.get("sensors")) and (registers := item.setdefault("registers", [])) is not None:
        registers.clear()
        for s in sensors:
            modify(s)
            if r := s.get("registers"):
                if enforce_parameters(s, parameters):
                    registers.extend(r)
                    if m := s.get("multiply"):
                        modify(m)
                        if m_r := m.get("registers"):
                            registers.extend(m_r)
                else:
                    s["registers"] = []

    g = dict(group)
    g.pop("items")
    bulk_inherit(item, g, *() if "registers" in item else REQUEST_UPDATE_INTERVAL)

    if not REQUEST_CODE in item and (r := item.get("registers")) and (addr := min(r)) is not None:
        item[REQUEST_CODE] = table.get(addr, code)

    if sensors := item.get("sensors"):
        for s in sensors:
            if s.get("registers"):
                bulk_inherit(s, item, REQUEST_CODE, "scale")
                if m := s.get("multiply"):
                    bulk_inherit(m, s, REQUEST_CODE, "scale")

    return item

def get_code(item, type, default = None):
    if REQUEST_CODE in item and (code := item[REQUEST_CODE]):
        if isinstance(code, int):
            if type == "read":
                return code
        elif type in code:
            return code[type]
    return default

def get_start_addr(data, code, addr):
    for d in data:
        if d[0] == code and d[1] <= addr < d[1] + len(data[d]):
            return d
    return None

def get_addr_value(data, code, addr):
    if (start := get_start_addr(data, code, addr)) is None:
        return None
    return data[start][addr - start[1]]

def ilen(object):
    return len(object) if not isinstance(object, int) else 1

def replace_first(object: str, newvalue, separator: str = ' '):
    return separator.join(filter(None, (newvalue, str(parts[1] if (parts := object.split(separator, 1)) and len(parts) > 1 else ''))))

def get_or_def(o, k, d):
    return o.get(k, d) or d

def from_bit_index(value):
    return 1 << value if not isinstance(value, list) else sum(1 << i for i in value)

def lookup_value(value, dictionary):
    default = dictionary[0]["value"]

    for o in dictionary:
        key = from_bit_index(o["bit"]) if "bit" in o else o["key"]

        if o.get("mode") == "|" and value & key == key:
            key = value
    
        if "default" in o or key == "default":
            default = o["value"]

        if key == value if not isinstance(key, list) else value in key:
            return o["value"]

    return default

def get_number(value, digits: int = -1):
    return int(value) if isinstance(value, int) or (isinstance(value, float) and value.is_integer()) else ((n if (n := round(value, digits)) and not n.is_integer() else int(n)) if digits > -1 else float(value))

def get_request_code(request: dict[str, int], default: int | None = None):
    return request[REQUEST_CODE] if REQUEST_CODE in request else request[REQUEST_CODE_ALT] if REQUEST_CODE_ALT in request else default

def get_tuple(tuple, index = 0):
    return tuple[index] if tuple else None

def split_p16b(value):
    while value:
        yield value & 0xFFFF
        value = value >> 16

def div_mod(dividend, divisor):
    return (dividend // divisor, dividend % divisor)

def concat_hex(value):
    return int(f"0x{value[0]:02}{value[1]:02}", 16)
