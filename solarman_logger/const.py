CONF_HOST = "host"
CONF_PORT = "port"
CONF_TRANSPORT = "transport"
CONF_LOOKUP_FILE = "lookup_file"
CONF_ADDITIONAL_OPTIONS = "additional_options"
CONF_MOD = "mod"
CONF_MPPT = "mppt"
CONF_PHASE = "phase"
CONF_PACK = "pack"
CONF_BATTERY_NOMINAL_VOLTAGE = "battery_nominal_voltage"
CONF_BATTERY_LIFE_CYCLE_RATING = "battery_life_cycle_rating"
CONF_MB_SLAVE_ID = "mb_slave_id"

UPDATE_INTERVAL = "update_interval"
IS_SINGLE_CODE = "is_single_code"
REGISTERS_CODE = "registers_code"
REGISTERS_MIN_SPAN = "registers_min_span"
REGISTERS_MAX_SIZE = "registers_max_size"
DIGITS = "digits"

DEFAULT_ = {
    "name": "Inverter",
    CONF_HOST: "",
    CONF_PORT: 8899,
    CONF_TRANSPORT: "tcp",
    CONF_MB_SLAVE_ID: 1,
    CONF_LOOKUP_FILE: "Auto",
    CONF_MOD: 0,
    CONF_MPPT: 4,
    CONF_PHASE: 3,
    CONF_PACK: -1,
    CONF_BATTERY_NOMINAL_VOLTAGE: 48,
    CONF_BATTERY_LIFE_CYCLE_RATING: 6000,
    UPDATE_INTERVAL: 60,
    IS_SINGLE_CODE: False,
    REGISTERS_CODE: 0x03,
    REGISTERS_MIN_SPAN: 25,
    REGISTERS_MAX_SIZE: 125,
    DIGITS: 6
}

PARAM_ = { CONF_MOD: CONF_MOD, CONF_MPPT: CONF_MPPT, CONF_PHASE: "l", CONF_PACK: CONF_PACK }

REQUEST_UPDATE_INTERVAL = UPDATE_INTERVAL
REQUEST_MIN_SPAN = "min_span"
REQUEST_MAX_SIZE = "max_size"
REQUEST_CODE = "code"
REQUEST_CODE_ALT = "mb_functioncode"
REQUEST_START = "start"
REQUEST_END = "end"
REQUEST_COUNT = "count"

DATETIME_FORMAT = "%y/%m/%d %H:%M:%S"
TIME_FORMAT = "%H:%M"
