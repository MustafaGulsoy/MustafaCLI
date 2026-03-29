"""Firmware skeleton generator for CubeSat OBC auto-design pipeline.

Generates compilable (with stubs) C firmware source files tailored to the
actual CubeSat design -- correct I2C addresses, UART baud rates, SPI chip
selects, task scheduling, and driver stubs for every selected subsystem.

The output is a complete project directory ready for ARM cross-compilation
targeting STM32F4-class microcontrollers.
"""
from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..bus_generator import PIN_TEMPLATES
from ..cubesat_wizard import COMPONENT_CATALOG, CubeSatDesign

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# I2C address map -- fixed addresses per subsystem component
# ---------------------------------------------------------------------------

I2C_ADDRESS_MAP: dict[str, int] = {
    "eps_pcu": 0x18,
    "adcs_unit": 0x1A,
    "gps_rx": 0x42,
    "prop_unit": 0x2C,
}

# UART configuration per component
UART_CONFIG: dict[str, dict[str, Any]] = {
    "com_uhf_trx": {"baud": 9600, "label": "UHF", "instance": "USART2"},
    "com_sband_tx": {"baud": 115200, "label": "SBAND", "instance": "USART3"},
}

# SPI configuration per component
SPI_CONFIG: dict[str, dict[str, Any]] = {
    "payload_main": {"cs_pin": "PA4", "label": "PAYLOAD", "instance": "SPI1"},
    "com_sband_tx": {"cs_pin": "PA15", "label": "SBAND", "instance": "SPI1"},
}

# Task periods in milliseconds
TASK_PERIODS: dict[str, int] = {
    "housekeeping": 1000,
    "telemetry": 5000,
    "payload": 10000,
    "adcs": 500,
    "gps": 2000,
    "thermal": 3000,
    "propulsion": 5000,
}

# Pin mapping for STM32F4
STM32_PIN_MAP: dict[str, dict[str, str]] = {
    "I2C1": {"SDA": "PB7", "SCL": "PB6"},
    "USART2": {"TX": "PA2", "RX": "PA3"},
    "USART3": {"TX": "PB10", "RX": "PB11"},
    "SPI1": {"MOSI": "PA7", "MISO": "PA6", "SCK": "PA5"},
    "LED": {"STATUS": "PC13"},
    "WATCHDOG": {"KICK": "PB0"},
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FirmwareResult:
    """Result of firmware generation containing output metadata."""

    files: list[str] = field(default_factory=list)
    main_file: str = ""
    total_lines: int = 0

    @property
    def file_count(self) -> int:
        """Number of generated files."""
        return len(self.files)

    def summary(self) -> str:
        """Human-readable generation summary."""
        return (
            f"Generated {self.file_count} files ({self.total_lines} lines total). "
            f"Main: {self.main_file}"
        )


# ---------------------------------------------------------------------------
# Subsystem metadata helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _SubsystemInfo:
    """Resolved subsystem metadata used during code generation."""

    id: str
    name: str
    has_i2c: bool
    has_uart: bool
    has_spi: bool
    i2c_addr: int | None
    uart_baud: int | None
    uart_instance: str | None
    spi_cs_pin: str | None
    spi_instance: str | None
    components: list[dict[str, Any]]


def _resolve_subsystem_info(design: CubeSatDesign) -> list[_SubsystemInfo]:
    """Build subsystem info list from design, only for selected subsystems."""
    result: list[_SubsystemInfo] = []

    for ss_id in design.subsystems:
        catalog_entry = COMPONENT_CATALOG.get(ss_id)
        if catalog_entry is None:
            continue

        components = catalog_entry["components"]
        comp_ids = [c["id"] for c in components]

        has_i2c = any(cid in I2C_ADDRESS_MAP for cid in comp_ids)
        has_uart = any(cid in UART_CONFIG for cid in comp_ids)
        has_spi = any(cid in SPI_CONFIG for cid in comp_ids)

        i2c_addr: int | None = None
        uart_baud: int | None = None
        uart_instance: str | None = None
        spi_cs_pin: str | None = None
        spi_instance: str | None = None

        for cid in comp_ids:
            if cid in I2C_ADDRESS_MAP:
                i2c_addr = I2C_ADDRESS_MAP[cid]
            if cid in UART_CONFIG:
                uart_baud = UART_CONFIG[cid]["baud"]
                uart_instance = UART_CONFIG[cid]["instance"]
            if cid in SPI_CONFIG:
                spi_cs_pin = SPI_CONFIG[cid]["cs_pin"]
                spi_instance = SPI_CONFIG[cid]["instance"]

        result.append(_SubsystemInfo(
            id=ss_id,
            name=catalog_entry["name"],
            has_i2c=has_i2c,
            has_uart=has_uart,
            has_spi=has_spi,
            i2c_addr=i2c_addr,
            uart_baud=uart_baud,
            uart_instance=uart_instance,
            spi_cs_pin=spi_cs_pin,
            spi_instance=spi_instance,
            components=components,
        ))

    return result


# ---------------------------------------------------------------------------
# Code generators -- one per output file
# ---------------------------------------------------------------------------

def _sanitize_name(name: str) -> str:
    """Convert mission name to a C-safe identifier."""
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).upper()


def _header_guard(filename: str) -> str:
    """Generate a header guard macro from filename."""
    return filename.replace(".", "_").upper() + "_"


def _gen_obc_main(design: CubeSatDesign, subs: list[_SubsystemInfo]) -> str:
    """Generate obc_main.c -- the main OBC firmware entry point."""
    safe_name = _sanitize_name(design.mission_name)
    subsystem_names = [s.name for s in subs]

    # Collect includes
    includes = [
        '#include <stdint.h>',
        '#include <stdbool.h>',
        '#include "hal.h"',
        '#include "scheduler.h"',
    ]

    has_i2c = any(s.has_i2c for s in subs)
    has_uart = any(s.has_uart for s in subs)
    has_spi = any(s.has_spi for s in subs)

    if has_i2c:
        includes.append('#include "i2c_bus.h"')
    if has_uart:
        includes.append('#include "uart_bus.h"')
    if has_spi:
        includes.append('#include "spi_bus.h"')

    # Subsystem driver includes
    driver_includes: list[str] = []
    for s in subs:
        if s.id == "obc":
            continue
        driver_includes.append(f'#include "{s.id}_driver.h"')

    # Payload always included
    driver_includes.append('#include "payload_driver.h"')

    # I2C address defines
    addr_defines: list[str] = []
    for s in subs:
        if s.i2c_addr is not None:
            addr_defines.append(
                f"#define {s.name.upper().replace(' ', '_')}_ADDR    0x{s.i2c_addr:02X}"
            )

    # Task period defines
    period_defines = [
        f"#define HOUSEKEEPING_PERIOD  {TASK_PERIODS['housekeeping']}",
        f"#define TELEMETRY_PERIOD     {TASK_PERIODS['telemetry']}",
        f"#define PAYLOAD_PERIOD       {TASK_PERIODS['payload']}",
    ]
    if any(s.id == "adcs" for s in subs):
        period_defines.append(f"#define ADCS_PERIOD          {TASK_PERIODS['adcs']}")
    if any(s.id == "gps" for s in subs):
        period_defines.append(f"#define GPS_PERIOD           {TASK_PERIODS['gps']}")
    if any(s.id == "thermal" for s in subs):
        period_defines.append(f"#define THERMAL_PERIOD       {TASK_PERIODS['thermal']}")
    if any(s.id == "propulsion" for s in subs):
        period_defines.append(f"#define PROPULSION_PERIOD    {TASK_PERIODS['propulsion']}")

    # Housekeeping task body
    hk_calls: list[str] = []
    if any(s.id == "eps" for s in subs):
        hk_calls.extend([
            "    eps_read_voltage();",
            "    eps_read_current();",
            "    eps_read_battery_soc();",
        ])
    if any(s.id == "adcs" for s in subs):
        hk_calls.append("    adcs_read_attitude();")
    if any(s.id == "gps" for s in subs):
        hk_calls.append("    gps_read_position();")
    if any(s.id == "thermal" for s in subs):
        hk_calls.append("    thermal_read_temps();")
    hk_calls.append("    obc_update_watchdog();")

    # Telemetry task body
    tlm_calls: list[str] = []
    if any(s.id == "com_uhf" for s in subs):
        tlm_calls.append("    uhf_send_beacon();")
    if any(s.id == "com_sband" for s in subs):
        tlm_calls.append("    sband_send_telemetry();")

    # Payload task body
    payload_type = design.payload_type
    if "Camera" in payload_type or "EO" in payload_type:
        payload_calls = [
            "    payload_capture_image();",
            "    payload_store_data();",
        ]
    elif "SDR" in payload_type or "Comms" in payload_type:
        payload_calls = [
            "    payload_sdr_sample();",
            "    payload_store_data();",
        ]
    elif "AIS" in payload_type:
        payload_calls = [
            "    payload_ais_decode();",
            "    payload_store_data();",
        ]
    elif "IoT" in payload_type:
        payload_calls = [
            "    payload_iot_poll();",
            "    payload_store_data();",
        ]
    else:
        payload_calls = [
            "    payload_acquire();",
            "    payload_store_data();",
        ]

    # Init calls in main()
    init_calls = [
        "    hal_init();",
        "    led_init();",
        "    watchdog_init();",
    ]
    if has_i2c:
        init_calls.append("    i2c_init();")
    if has_uart:
        for s in subs:
            if s.uart_baud is not None:
                init_calls.append(f"    uart_init({s.uart_baud});  /* {s.name} */")
    if has_spi:
        init_calls.append("    spi_init();")

    # Subsystem init calls
    for s in subs:
        if s.id == "obc":
            continue
        init_calls.append(f"    {s.id}_init();")
    init_calls.append("    payload_init();")

    # Scheduler registrations
    sched_calls = [
        "    scheduler_add(task_housekeeping, HOUSEKEEPING_PERIOD);",
        "    scheduler_add(task_telemetry, TELEMETRY_PERIOD);",
        "    scheduler_add(task_payload, PAYLOAD_PERIOD);",
    ]
    if any(s.id == "adcs" for s in subs):
        sched_calls.append("    scheduler_add(task_adcs, ADCS_PERIOD);")
    if any(s.id == "gps" for s in subs):
        sched_calls.append("    scheduler_add(task_gps, GPS_PERIOD);")
    if any(s.id == "thermal" for s in subs):
        sched_calls.append("    scheduler_add(task_thermal, THERMAL_PERIOD);")
    if any(s.id == "propulsion" for s in subs):
        sched_calls.append("    scheduler_add(task_propulsion, PROPULSION_PERIOD);")

    # Extra task functions
    extra_tasks: list[str] = []
    if any(s.id == "adcs" for s in subs):
        extra_tasks.append(textwrap.dedent("""\
            void task_adcs(void) {
                adcs_update_control();
            }
        """))
    if any(s.id == "gps" for s in subs):
        extra_tasks.append(textwrap.dedent("""\
            void task_gps(void) {
                gps_read_position();
                gps_update_time();
            }
        """))
    if any(s.id == "thermal" for s in subs):
        extra_tasks.append(textwrap.dedent("""\
            void task_thermal(void) {
                thermal_read_temps();
                thermal_control_heaters();
            }
        """))
    if any(s.id == "propulsion" for s in subs):
        extra_tasks.append(textwrap.dedent("""\
            void task_propulsion(void) {
                prop_check_pressure();
            }
        """))

    lines: list[str] = []
    lines.append(f"/* {design.mission_name} OBC Firmware")
    lines.append(f" * Auto-generated by SAT-MAESTRO Firmware Generator")
    lines.append(f" * Subsystems: {', '.join(subsystem_names)}")
    lines.append(f" * Payload: {design.payload_type}")
    lines.append(f" *")
    lines.append(f" * Target: STM32F4 (ARM Cortex-M4)")
    lines.append(f" * WARNING: This is skeleton code. Implement hardware-specific")
    lines.append(f" *          register access before flight use.")
    lines.append(f" */")
    lines.append("")
    lines.extend(includes)
    lines.append("")
    lines.extend(driver_includes)
    lines.append("")
    lines.append("/* ---- Subsystem I2C addresses ---- */")
    if addr_defines:
        lines.extend(addr_defines)
    else:
        lines.append("/* No I2C subsystems selected */")
    lines.append("")
    lines.append("/* ---- Task periods (ms) ---- */")
    lines.extend(period_defines)
    lines.append("")
    lines.append("/* ---- Global state ---- */")
    lines.append(f"static const char MISSION_NAME[] = \"{design.mission_name}\";")
    lines.append(f"static volatile uint32_t uptime_ms = 0;")
    lines.append(f"static volatile bool safe_mode = false;")
    lines.append("")
    lines.append("/* ---- Task implementations ---- */")
    lines.append("")
    lines.append("void task_housekeeping(void) {")
    lines.extend(hk_calls)
    lines.append("}")
    lines.append("")
    lines.append("void task_telemetry(void) {")
    if tlm_calls:
        lines.extend(tlm_calls)
    else:
        lines.append("    /* No communication subsystem selected */")
    lines.append("}")
    lines.append("")
    lines.append("void task_payload(void) {")
    lines.extend(payload_calls)
    lines.append("}")
    lines.append("")
    for task_block in extra_tasks:
        lines.append(task_block)

    lines.append("/* ---- Safe mode handler ---- */")
    lines.append("")
    lines.append("void enter_safe_mode(void) {")
    lines.append("    safe_mode = true;")
    lines.append("    /* Disable non-essential subsystems */")
    lines.append("    payload_shutdown();")
    if any(s.id == "com_sband" for s in subs):
        lines.append("    sband_shutdown();")
    if any(s.id == "propulsion" for s in subs):
        lines.append("    prop_shutdown();")
    lines.append("    /* Keep EPS, OBC, and UHF beacon alive */")
    lines.append("}")
    lines.append("")
    lines.append("/* ---- Entry point ---- */")
    lines.append("")
    lines.append("int main(void) {")
    lines.extend(init_calls)
    lines.append("")
    lines.append("    /* Register periodic tasks */")
    lines.extend(sched_calls)
    lines.append("")
    lines.append("    /* Main scheduler loop (never returns) */")
    lines.append("    scheduler_run();")
    lines.append("    return 0;")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def _gen_hal_h(design: CubeSatDesign, subs: list[_SubsystemInfo]) -> str:
    """Generate hal.h -- hardware abstraction layer header."""
    guard = _header_guard("hal.h")

    has_i2c = any(s.has_i2c for s in subs)
    has_uart = any(s.has_uart for s in subs)
    has_spi = any(s.has_spi for s in subs)

    # Pin definitions based on active peripherals
    pin_defs: list[str] = []
    pin_defs.append("/* Status LED */")
    pin_defs.append(f"#define PIN_LED_STATUS       {STM32_PIN_MAP['LED']['STATUS']}")
    pin_defs.append(f"#define PIN_WATCHDOG_KICK    {STM32_PIN_MAP['WATCHDOG']['KICK']}")
    pin_defs.append("")

    if has_i2c:
        pin_defs.append("/* I2C1 bus pins */")
        pin_defs.append(f"#define PIN_I2C1_SDA         {STM32_PIN_MAP['I2C1']['SDA']}")
        pin_defs.append(f"#define PIN_I2C1_SCL         {STM32_PIN_MAP['I2C1']['SCL']}")
        pin_defs.append("")

    if has_uart:
        for s in subs:
            if s.uart_instance is not None:
                mapping = STM32_PIN_MAP.get(s.uart_instance, {})
                label = UART_CONFIG.get(
                    next((c["id"] for c in s.components if c["id"] in UART_CONFIG), ""),
                    {},
                ).get("label", s.name.upper())
                pin_defs.append(f"/* {s.uart_instance} -- {label} */")
                if "TX" in mapping:
                    pin_defs.append(
                        f"#define PIN_{s.uart_instance}_TX        {mapping['TX']}"
                    )
                if "RX" in mapping:
                    pin_defs.append(
                        f"#define PIN_{s.uart_instance}_RX        {mapping['RX']}"
                    )
                pin_defs.append("")

    if has_spi:
        mapping = STM32_PIN_MAP.get("SPI1", {})
        pin_defs.append("/* SPI1 bus pins */")
        pin_defs.append(f"#define PIN_SPI1_MOSI        {mapping.get('MOSI', 'PA7')}")
        pin_defs.append(f"#define PIN_SPI1_MISO        {mapping.get('MISO', 'PA6')}")
        pin_defs.append(f"#define PIN_SPI1_SCK         {mapping.get('SCK', 'PA5')}")
        pin_defs.append("")
        for s in subs:
            if s.spi_cs_pin is not None:
                label = SPI_CONFIG.get(
                    next((c["id"] for c in s.components if c["id"] in SPI_CONFIG), ""),
                    {},
                ).get("label", s.name.upper())
                pin_defs.append(f"#define PIN_CS_{label:<16s} {s.spi_cs_pin}")
        # Payload CS
        if "payload_main" in SPI_CONFIG:
            pin_defs.append(
                f"#define PIN_CS_PAYLOAD           "
                f"{SPI_CONFIG['payload_main']['cs_pin']}"
            )
        pin_defs.append("")

    # Clock config
    obc_comp = COMPONENT_CATALOG.get("obc", {}).get("components", [{}])[0]
    cpu_name = obc_comp.get("properties", {}).get("cpu", "ARM Cortex-M4")

    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* {design.mission_name} Hardware Abstraction Layer",
        f" * Auto-generated by SAT-MAESTRO",
        f" * Target MCU: STM32F4 ({cpu_name})",
        " */",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        "/* ---- System clock ---- */",
        "#define SYSCLK_HZ            168000000UL  /* 168 MHz */",
        "#define APB1_HZ              42000000UL",
        "#define APB2_HZ              84000000UL",
        "#define SYSTICK_HZ           1000          /* 1 ms tick */",
        "",
        "/* ---- Pin definitions ---- */",
        *pin_defs,
        "/* ---- Function prototypes ---- */",
        "",
        "/**",
        " * Initialize system clocks, GPIO, NVIC, and SysTick.",
        " */",
        "void hal_init(void);",
        "",
        "/**",
        " * Initialize status LED GPIO.",
        " */",
        "void led_init(void);",
        "",
        "/**",
        " * Toggle status LED.",
        " */",
        "void led_toggle(void);",
        "",
        "/**",
        " * Initialize independent watchdog timer.",
        " */",
        "void watchdog_init(void);",
        "",
        "/**",
        " * Kick the watchdog to prevent reset.",
        " */",
        "void obc_update_watchdog(void);",
        "",
        "/**",
        " * Get system uptime in milliseconds.",
        " */",
        "uint32_t hal_get_tick(void);",
        "",
        "/**",
        " * Millisecond busy-wait delay.",
        " */",
        "void hal_delay_ms(uint32_t ms);",
        "",
        f"#endif /* {guard} */",
        "",
    ]

    return "\n".join(lines)


def _gen_hal_c(design: CubeSatDesign) -> str:
    """Generate hal.c -- HAL implementation stubs."""
    lines = [
        f"/* {design.mission_name} HAL Implementation",
        " * Auto-generated by SAT-MAESTRO",
        " *",
        " * TODO: Replace stubs with STM32 HAL or register-level code.",
        " */",
        "",
        '#include "hal.h"',
        "",
        "static volatile uint32_t tick_count = 0;",
        "",
        "/* SysTick interrupt handler -- called every 1 ms */",
        "void SysTick_Handler(void) {",
        "    tick_count++;",
        "}",
        "",
        "void hal_init(void) {",
        "    /* TODO: Configure system clocks (HSE -> PLL -> 168 MHz) */",
        "    /* TODO: Enable GPIO port clocks */",
        "    /* TODO: Configure SysTick for 1 ms interrupts */",
        "}",
        "",
        "void led_init(void) {",
        "    /* TODO: Configure PIN_LED_STATUS as push-pull output */",
        "}",
        "",
        "void led_toggle(void) {",
        "    /* TODO: Toggle PIN_LED_STATUS */",
        "}",
        "",
        "void watchdog_init(void) {",
        "    /* TODO: Configure IWDG with ~4 second timeout */",
        "}",
        "",
        "void obc_update_watchdog(void) {",
        "    /* TODO: Reload IWDG counter */",
        "}",
        "",
        "uint32_t hal_get_tick(void) {",
        "    return tick_count;",
        "}",
        "",
        "void hal_delay_ms(uint32_t ms) {",
        "    uint32_t start = tick_count;",
        "    while ((tick_count - start) < ms) {",
        "        /* spin */",
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


def _gen_scheduler_h() -> str:
    """Generate scheduler.h -- cooperative task scheduler."""
    guard = _header_guard("scheduler.h")
    return "\n".join([
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "/* Cooperative round-robin task scheduler",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        "#include <stdint.h>",
        "",
        "/** Maximum number of scheduled tasks. */",
        "#define SCHEDULER_MAX_TASKS  16",
        "",
        "/** Function pointer type for scheduled tasks. */",
        "typedef void (*task_fn_t)(void);",
        "",
        "/**",
        " * Register a periodic task.",
        " *",
        " * @param fn       Task function pointer.",
        " * @param period   Execution period in milliseconds.",
        " */",
        "void scheduler_add(task_fn_t fn, uint32_t period);",
        "",
        "/**",
        " * Run the scheduler loop. This function never returns.",
        " */",
        "void scheduler_run(void);",
        "",
        f"#endif /* {guard} */",
        "",
    ])


def _gen_scheduler_c() -> str:
    """Generate scheduler.c -- cooperative scheduler implementation."""
    return "\n".join([
        "/* Cooperative task scheduler implementation",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        '#include "scheduler.h"',
        '#include "hal.h"',
        "",
        "typedef struct {",
        "    task_fn_t fn;",
        "    uint32_t period;",
        "    uint32_t last_run;",
        "} task_entry_t;",
        "",
        "static task_entry_t tasks[SCHEDULER_MAX_TASKS];",
        "static uint8_t task_count = 0;",
        "",
        "void scheduler_add(task_fn_t fn, uint32_t period) {",
        "    if (task_count >= SCHEDULER_MAX_TASKS) {",
        "        return;  /* silently drop -- production code should assert */",
        "    }",
        "    tasks[task_count].fn = fn;",
        "    tasks[task_count].period = period;",
        "    tasks[task_count].last_run = 0;",
        "    task_count++;",
        "}",
        "",
        "void scheduler_run(void) {",
        "    while (1) {",
        "        uint32_t now = hal_get_tick();",
        "        for (uint8_t i = 0; i < task_count; i++) {",
        "            if ((now - tasks[i].last_run) >= tasks[i].period) {",
        "                tasks[i].fn();",
        "                tasks[i].last_run = now;",
        "            }",
        "        }",
        "    }",
        "}",
        "",
    ])


def _gen_i2c_h() -> str:
    """Generate i2c_bus.h -- I2C bus driver header."""
    guard = _header_guard("i2c_bus.h")
    return "\n".join([
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "/* I2C bus driver for CubeSat OBC",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        "/** I2C bus status codes. */",
        "typedef enum {",
        "    I2C_OK = 0,",
        "    I2C_ERR_NACK,",
        "    I2C_ERR_BUS,",
        "    I2C_ERR_TIMEOUT,",
        "} i2c_status_t;",
        "",
        "/**",
        " * Initialize I2C1 peripheral at 100 kHz standard mode.",
        " */",
        "void i2c_init(void);",
        "",
        "/**",
        " * Write data to an I2C slave.",
        " *",
        " * @param addr   7-bit slave address.",
        " * @param data   Pointer to transmit buffer.",
        " * @param len    Number of bytes to write.",
        " * @return       I2C status code.",
        " */",
        "i2c_status_t i2c_write(uint8_t addr, const uint8_t *data, uint16_t len);",
        "",
        "/**",
        " * Read data from an I2C slave.",
        " *",
        " * @param addr   7-bit slave address.",
        " * @param buf    Pointer to receive buffer.",
        " * @param len    Number of bytes to read.",
        " * @return       I2C status code.",
        " */",
        "i2c_status_t i2c_read(uint8_t addr, uint8_t *buf, uint16_t len);",
        "",
        "/**",
        " * Write a register then read response (combined transaction).",
        " *",
        " * @param addr     7-bit slave address.",
        " * @param reg      Register address to write.",
        " * @param buf      Pointer to receive buffer.",
        " * @param len      Number of bytes to read.",
        " * @return         I2C status code.",
        " */",
        "i2c_status_t i2c_write_read(uint8_t addr, uint8_t reg, "
        "uint8_t *buf, uint16_t len);",
        "",
        f"#endif /* {guard} */",
        "",
    ])


def _gen_i2c_c() -> str:
    """Generate i2c_bus.c -- I2C driver implementation."""
    return "\n".join([
        "/* I2C bus driver implementation",
        " * Auto-generated by SAT-MAESTRO",
        " *",
        " * TODO: Replace stubs with STM32 I2C register access or HAL calls.",
        " */",
        "",
        '#include "i2c_bus.h"',
        '#include "hal.h"',
        "",
        "#define I2C_TIMEOUT_MS  100",
        "",
        "void i2c_init(void) {",
        "    /* TODO: Enable I2C1 clock */",
        "    /* TODO: Configure I2C1 GPIO (SDA, SCL) as AF open-drain */",
        "    /* TODO: Set I2C timing for 100 kHz */",
        "    /* TODO: Enable I2C1 peripheral */",
        "}",
        "",
        "i2c_status_t i2c_write(uint8_t addr, const uint8_t *data, uint16_t len) {",
        "    /* TODO: Send START, address+W, data bytes, STOP */",
        "    (void)addr;",
        "    (void)data;",
        "    (void)len;",
        "    return I2C_OK;",
        "}",
        "",
        "i2c_status_t i2c_read(uint8_t addr, uint8_t *buf, uint16_t len) {",
        "    /* TODO: Send START, address+R, read data bytes, NACK last, STOP */",
        "    (void)addr;",
        "    (void)buf;",
        "    (void)len;",
        "    return I2C_OK;",
        "}",
        "",
        "i2c_status_t i2c_write_read(uint8_t addr, uint8_t reg, "
        "uint8_t *buf, uint16_t len) {",
        "    i2c_status_t status = i2c_write(addr, &reg, 1);",
        "    if (status != I2C_OK) {",
        "        return status;",
        "    }",
        "    return i2c_read(addr, buf, len);",
        "}",
        "",
    ])


def _gen_uart_h() -> str:
    """Generate uart_bus.h -- UART driver header."""
    guard = _header_guard("uart_bus.h")
    return "\n".join([
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "/* UART bus driver for CubeSat OBC",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        "/** UART status codes. */",
        "typedef enum {",
        "    UART_OK = 0,",
        "    UART_ERR_OVERRUN,",
        "    UART_ERR_FRAMING,",
        "    UART_ERR_TIMEOUT,",
        "} uart_status_t;",
        "",
        "/**",
        " * Initialize UART peripheral.",
        " *",
        " * @param baud   Baud rate (e.g. 9600, 115200).",
        " */",
        "void uart_init(uint32_t baud);",
        "",
        "/**",
        " * Transmit data over UART.",
        " *",
        " * @param data   Pointer to transmit buffer.",
        " * @param len    Number of bytes to send.",
        " * @return       UART status code.",
        " */",
        "uart_status_t uart_send(const uint8_t *data, uint16_t len);",
        "",
        "/**",
        " * Receive data from UART (blocking with timeout).",
        " *",
        " * @param buf        Pointer to receive buffer.",
        " * @param len        Maximum bytes to read.",
        " * @param timeout_ms Timeout in milliseconds.",
        " * @return           Number of bytes actually received.",
        " */",
        "uint16_t uart_receive(uint8_t *buf, uint16_t len, uint32_t timeout_ms);",
        "",
        "/**",
        " * Check if receive data is available.",
        " *",
        " * @return  true if at least one byte is in the RX buffer.",
        " */",
        "bool uart_rx_available(void);",
        "",
        f"#endif /* {guard} */",
        "",
    ])


def _gen_uart_c() -> str:
    """Generate uart_bus.c -- UART driver implementation."""
    return "\n".join([
        "/* UART bus driver implementation",
        " * Auto-generated by SAT-MAESTRO",
        " *",
        " * TODO: Replace stubs with STM32 USART register access.",
        " */",
        "",
        '#include "uart_bus.h"',
        '#include "hal.h"',
        "",
        "#define UART_RX_BUF_SIZE  256",
        "",
        "static uint8_t rx_buffer[UART_RX_BUF_SIZE];",
        "static volatile uint16_t rx_head = 0;",
        "static volatile uint16_t rx_tail = 0;",
        "",
        "void uart_init(uint32_t baud) {",
        "    /* TODO: Enable USARTx clock */",
        "    /* TODO: Configure TX/RX GPIO as alternate function */",
        "    /* TODO: Set baud rate divider */",
        "    /* TODO: Enable TX, RX, and RXNE interrupt */",
        "    (void)baud;",
        "}",
        "",
        "uart_status_t uart_send(const uint8_t *data, uint16_t len) {",
        "    /* TODO: Transmit each byte, waiting for TXE flag */",
        "    (void)data;",
        "    (void)len;",
        "    return UART_OK;",
        "}",
        "",
        "uint16_t uart_receive(uint8_t *buf, uint16_t len, uint32_t timeout_ms) {",
        "    uint16_t count = 0;",
        "    uint32_t start = hal_get_tick();",
        "    while (count < len && (hal_get_tick() - start) < timeout_ms) {",
        "        if (rx_head != rx_tail) {",
        "            buf[count++] = rx_buffer[rx_tail];",
        "            rx_tail = (rx_tail + 1) % UART_RX_BUF_SIZE;",
        "        }",
        "    }",
        "    return count;",
        "}",
        "",
        "bool uart_rx_available(void) {",
        "    return rx_head != rx_tail;",
        "}",
        "",
        "/* USART IRQ handler -- place in vector table */",
        "void USARTx_IRQHandler(void) {",
        "    /* TODO: Check RXNE flag, read data register into rx_buffer */",
        "    /* uint8_t byte = USART->DR; */",
        "    /* rx_buffer[rx_head] = byte; */",
        "    /* rx_head = (rx_head + 1) % UART_RX_BUF_SIZE; */",
        "}",
        "",
    ])


def _gen_spi_h() -> str:
    """Generate spi_bus.h -- SPI driver header."""
    guard = _header_guard("spi_bus.h")
    return "\n".join([
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        "/* SPI bus driver for CubeSat OBC",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        "#include <stdint.h>",
        "",
        "/** SPI status codes. */",
        "typedef enum {",
        "    SPI_OK = 0,",
        "    SPI_ERR_BUSY,",
        "    SPI_ERR_OVERRUN,",
        "    SPI_ERR_TIMEOUT,",
        "} spi_status_t;",
        "",
        "/**",
        " * Initialize SPI1 peripheral (master mode, CPOL=0, CPHA=0).",
        " */",
        "void spi_init(void);",
        "",
        "/**",
        " * Assert chip-select for a given device.",
        " *",
        " * @param cs_pin   GPIO pin identifier for chip select.",
        " */",
        "void spi_cs_low(uint8_t cs_pin);",
        "",
        "/**",
        " * Deassert chip-select.",
        " *",
        " * @param cs_pin   GPIO pin identifier for chip select.",
        " */",
        "void spi_cs_high(uint8_t cs_pin);",
        "",
        "/**",
        " * Full-duplex SPI transfer.",
        " *",
        " * @param tx_data   Pointer to transmit buffer.",
        " * @param rx_data   Pointer to receive buffer (may be NULL).",
        " * @param len       Number of bytes to transfer.",
        " * @return          SPI status code.",
        " */",
        "spi_status_t spi_transfer(const uint8_t *tx_data, uint8_t *rx_data, "
        "uint16_t len);",
        "",
        "/**",
        " * Write data to SPI (ignore received data).",
        " */",
        "spi_status_t spi_write(const uint8_t *data, uint16_t len);",
        "",
        "/**",
        " * Read data from SPI (send 0xFF clock bytes).",
        " */",
        "spi_status_t spi_read(uint8_t *buf, uint16_t len);",
        "",
        f"#endif /* {guard} */",
        "",
    ])


def _gen_spi_c() -> str:
    """Generate spi_bus.c -- SPI driver implementation."""
    return "\n".join([
        "/* SPI bus driver implementation",
        " * Auto-generated by SAT-MAESTRO",
        " *",
        " * TODO: Replace stubs with STM32 SPI register access.",
        " */",
        "",
        '#include "spi_bus.h"',
        '#include "hal.h"',
        "",
        "void spi_init(void) {",
        "    /* TODO: Enable SPI1 clock */",
        "    /* TODO: Configure MOSI, MISO, SCK as alternate function */",
        "    /* TODO: Configure CS pins as push-pull output, default HIGH */",
        "    /* TODO: Set SPI master mode, 8-bit, CPOL=0, CPHA=0 */",
        "    /* TODO: Set prescaler for desired clock speed */",
        "    /* TODO: Enable SPI peripheral */",
        "}",
        "",
        "void spi_cs_low(uint8_t cs_pin) {",
        "    /* TODO: Clear the GPIO pin */",
        "    (void)cs_pin;",
        "}",
        "",
        "void spi_cs_high(uint8_t cs_pin) {",
        "    /* TODO: Set the GPIO pin */",
        "    (void)cs_pin;",
        "}",
        "",
        "spi_status_t spi_transfer(const uint8_t *tx_data, uint8_t *rx_data, "
        "uint16_t len) {",
        "    /* TODO: For each byte: write to DR, wait for RXNE, read DR */",
        "    (void)tx_data;",
        "    (void)rx_data;",
        "    (void)len;",
        "    return SPI_OK;",
        "}",
        "",
        "spi_status_t spi_write(const uint8_t *data, uint16_t len) {",
        "    return spi_transfer(data, (void *)0, len);",
        "}",
        "",
        "spi_status_t spi_read(uint8_t *buf, uint16_t len) {",
        "    /* Send 0xFF as clock bytes while reading */",
        "    uint8_t dummy[1] = {0xFF};",
        "    (void)dummy;",
        "    return spi_transfer((void *)0, buf, len);",
        "}",
        "",
    ])


def _gen_eps_driver_h(design: CubeSatDesign) -> str:
    """Generate eps_driver.h -- EPS subsystem interface."""
    guard = _header_guard("eps_driver.h")
    addr = I2C_ADDRESS_MAP.get("eps_pcu", 0x18)
    catalog = COMPONENT_CATALOG["eps"]
    batt_comp = next(
        (c for c in catalog["components"] if c["id"] == "eps_batt"), None
    )
    capacity_wh = batt_comp["properties"]["capacity_wh"] if batt_comp else 20

    return "\n".join([
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* EPS driver for {design.mission_name}",
        " * Auto-generated by SAT-MAESTRO",
        f" * I2C Address: 0x{addr:02X}",
        " */",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        f"#define EPS_I2C_ADDR         0x{addr:02X}",
        f"#define EPS_BATTERY_CAPACITY {capacity_wh}  /* Wh */",
        "",
        "/* EPS register map */",
        "#define EPS_REG_VBATT        0x00",
        "#define EPS_REG_IBATT        0x01",
        "#define EPS_REG_VSOLAR       0x02",
        "#define EPS_REG_ISOLAR       0x03",
        "#define EPS_REG_TEMP         0x04",
        "#define EPS_REG_SOC          0x05",
        "#define EPS_REG_STATUS       0x06",
        "#define EPS_REG_POWER_MODE   0x10",
        "",
        "/** EPS power modes. */",
        "typedef enum {",
        "    EPS_MODE_NORMAL = 0,",
        "    EPS_MODE_LOW_POWER,",
        "    EPS_MODE_CRITICAL,",
        "} eps_power_mode_t;",
        "",
        "/** EPS telemetry data. */",
        "typedef struct {",
        "    uint16_t vbatt_mv;      /* Battery voltage in mV */",
        "    int16_t  ibatt_ma;      /* Battery current in mA (neg = charging) */",
        "    uint16_t vsolar_mv;     /* Solar panel voltage in mV */",
        "    uint16_t isolar_ma;     /* Solar panel current in mA */",
        "    int8_t   temp_c;        /* Board temperature in deg C */",
        "    uint8_t  soc_pct;       /* State of charge 0-100% */",
        "    uint8_t  status;        /* Status register */",
        "} eps_telemetry_t;",
        "",
        "void eps_init(void);",
        "void eps_read_voltage(void);",
        "void eps_read_current(void);",
        "void eps_read_battery_soc(void);",
        "eps_telemetry_t eps_get_telemetry(void);",
        "void eps_set_power_mode(eps_power_mode_t mode);",
        "bool eps_is_battery_critical(void);",
        "",
        f"#endif /* {guard} */",
        "",
    ])


def _gen_eps_driver_c() -> str:
    """Generate eps_driver.c -- EPS driver implementation."""
    return "\n".join([
        "/* EPS driver implementation",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        '#include "eps_driver.h"',
        '#include "i2c_bus.h"',
        "",
        "static eps_telemetry_t telemetry;",
        "",
        "void eps_init(void) {",
        "    /* Verify EPS responds on I2C bus */",
        "    uint8_t dummy;",
        "    i2c_status_t status = i2c_write_read(",
        "        EPS_I2C_ADDR, EPS_REG_STATUS, &dummy, 1);",
        "    (void)status;",
        "}",
        "",
        "void eps_read_voltage(void) {",
        "    uint8_t buf[2];",
        "    if (i2c_write_read(EPS_I2C_ADDR, EPS_REG_VBATT, buf, 2) == I2C_OK) {",
        "        telemetry.vbatt_mv = (uint16_t)(buf[0] << 8) | buf[1];",
        "    }",
        "}",
        "",
        "void eps_read_current(void) {",
        "    uint8_t buf[2];",
        "    if (i2c_write_read(EPS_I2C_ADDR, EPS_REG_IBATT, buf, 2) == I2C_OK) {",
        "        telemetry.ibatt_ma = (int16_t)((buf[0] << 8) | buf[1]);",
        "    }",
        "}",
        "",
        "void eps_read_battery_soc(void) {",
        "    uint8_t buf[1];",
        "    if (i2c_write_read(EPS_I2C_ADDR, EPS_REG_SOC, buf, 1) == I2C_OK) {",
        "        telemetry.soc_pct = buf[0];",
        "    }",
        "}",
        "",
        "eps_telemetry_t eps_get_telemetry(void) {",
        "    return telemetry;",
        "}",
        "",
        "void eps_set_power_mode(eps_power_mode_t mode) {",
        "    uint8_t data[2] = {EPS_REG_POWER_MODE, (uint8_t)mode};",
        "    i2c_write(EPS_I2C_ADDR, data, 2);",
        "}",
        "",
        "bool eps_is_battery_critical(void) {",
        "    return telemetry.vbatt_mv < 6000;  /* Below 6.0V */",
        "}",
        "",
    ])


def _gen_subsystem_driver_h(
    ss_id: str,
    info: _SubsystemInfo,
    design: CubeSatDesign,
) -> str:
    """Generate a driver header for a non-EPS subsystem."""
    guard = _header_guard(f"{ss_id}_driver.h")
    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* {info.name} driver for {design.mission_name}",
        f" * Auto-generated by SAT-MAESTRO",
    ]

    if info.i2c_addr is not None:
        lines.append(f" * I2C Address: 0x{info.i2c_addr:02X}")
    if info.uart_baud is not None:
        lines.append(f" * UART Baud: {info.uart_baud}")
    if info.spi_cs_pin is not None:
        lines.append(f" * SPI CS: {info.spi_cs_pin}")
    lines.append(" */")
    lines.append("")
    lines.append("#include <stdint.h>")
    lines.append("#include <stdbool.h>")
    lines.append("")

    if info.i2c_addr is not None:
        lines.append(
            f"#define {ss_id.upper()}_I2C_ADDR  0x{info.i2c_addr:02X}"
        )
        lines.append("")

    # Subsystem-specific API based on type
    lines.append(f"void {ss_id}_init(void);")

    if ss_id == "adcs":
        lines.extend([
            "void adcs_read_attitude(void);",
            "void adcs_update_control(void);",
            "void adcs_get_quaternion(float q[4]);",
            "void adcs_set_target_attitude(float q[4]);",
        ])
    elif ss_id == "com_uhf":
        lines.extend([
            "void uhf_send_beacon(void);",
            "void uhf_send_packet(const uint8_t *data, uint16_t len);",
            "uint16_t uhf_receive_packet(uint8_t *buf, uint16_t max_len);",
            "int8_t uhf_get_rssi(void);",
        ])
    elif ss_id == "com_sband":
        lines.extend([
            "void sband_send_telemetry(void);",
            "void sband_send_data(const uint8_t *data, uint32_t len);",
            "void sband_shutdown(void);",
        ])
    elif ss_id == "gps":
        lines.extend([
            "void gps_read_position(void);",
            "void gps_update_time(void);",
            "",
            "typedef struct {",
            "    double latitude;",
            "    double longitude;",
            "    float  altitude_m;",
            "    uint8_t num_sats;",
            "    bool   fix_valid;",
            "} gps_position_t;",
            "",
            "gps_position_t gps_get_position(void);",
        ])
    elif ss_id == "propulsion":
        lines.extend([
            "void prop_check_pressure(void);",
            "void prop_fire_thruster(uint16_t duration_ms);",
            "void prop_shutdown(void);",
            "float prop_get_remaining_dv(void);",
        ])
    elif ss_id == "thermal":
        lines.extend([
            "void thermal_read_temps(void);",
            "void thermal_control_heaters(void);",
            "",
            "typedef struct {",
            "    int8_t zone_temp_c[2];",
            "    bool   heater_on[2];",
            "} thermal_status_t;",
            "",
            "thermal_status_t thermal_get_status(void);",
        ])

    lines.append("")
    lines.append(f"#endif /* {guard} */")
    lines.append("")
    return "\n".join(lines)


def _gen_subsystem_driver_c(
    ss_id: str,
    info: _SubsystemInfo,
) -> str:
    """Generate a driver implementation for a non-EPS subsystem."""
    lines = [
        f"/* {info.name} driver implementation",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        f'#include "{ss_id}_driver.h"',
    ]

    if info.has_i2c:
        lines.append('#include "i2c_bus.h"')
    if info.has_uart:
        lines.append('#include "uart_bus.h"')
    if info.has_spi:
        lines.append('#include "spi_bus.h"')

    lines.append("")

    # Init function
    lines.append(f"void {ss_id}_init(void) {{")
    if info.has_i2c and info.i2c_addr is not None:
        lines.append(f"    /* Verify {info.name} on I2C bus */")
        lines.append(f"    uint8_t dummy;")
        lines.append(
            f"    i2c_write_read(0x{info.i2c_addr:02X}, 0x00, &dummy, 1);"
        )
    if info.has_uart:
        lines.append(f"    /* {info.name} communicates over UART */")
    if info.has_spi:
        lines.append(f"    /* {info.name} communicates over SPI */")
    lines.append("}")
    lines.append("")

    # Subsystem-specific function stubs
    if ss_id == "adcs":
        lines.extend([
            "static float attitude_q[4] = {1.0f, 0.0f, 0.0f, 0.0f};",
            "",
            "void adcs_read_attitude(void) {",
            f"    uint8_t buf[16];",
            f"    if (i2c_write_read(0x{info.i2c_addr:02X}, 0x10, buf, 16)"
            " == I2C_OK) {",
            "        /* TODO: Parse quaternion from raw bytes */",
            "    }",
            "}",
            "",
            "void adcs_update_control(void) {",
            "    /* TODO: Run PD controller, command reaction wheels */",
            "}",
            "",
            "void adcs_get_quaternion(float q[4]) {",
            "    for (int i = 0; i < 4; i++) q[i] = attitude_q[i];",
            "}",
            "",
            "void adcs_set_target_attitude(float q[4]) {",
            "    (void)q;",
            "    /* TODO: Send target quaternion to ADCS unit */",
            "}",
            "",
        ])
    elif ss_id == "com_uhf":
        lines.extend([
            "void uhf_send_beacon(void) {",
            "    /* TODO: Format AX.25 beacon frame and transmit */",
            '    const uint8_t beacon[] = "CQ CQ DE SAT";',
            "    uart_send(beacon, sizeof(beacon) - 1);",
            "}",
            "",
            "void uhf_send_packet(const uint8_t *data, uint16_t len) {",
            "    uart_send(data, len);",
            "}",
            "",
            "uint16_t uhf_receive_packet(uint8_t *buf, uint16_t max_len) {",
            "    return uart_receive(buf, max_len, 1000);",
            "}",
            "",
            "int8_t uhf_get_rssi(void) {",
            "    /* TODO: Query transceiver RSSI register */",
            "    return -80;",
            "}",
            "",
        ])
    elif ss_id == "com_sband":
        lines.extend([
            "void sband_send_telemetry(void) {",
            "    /* TODO: Format and transmit S-band telemetry frame via SPI */",
            "}",
            "",
            "void sband_send_data(const uint8_t *data, uint32_t len) {",
            "    (void)data;",
            "    (void)len;",
            "    /* TODO: Chunk data and send via SPI */",
            "}",
            "",
            "void sband_shutdown(void) {",
            "    /* TODO: Power-down S-band transmitter */",
            "}",
            "",
        ])
    elif ss_id == "gps":
        lines.extend([
            "static gps_position_t position = {0};",
            "",
            "void gps_read_position(void) {",
            f"    uint8_t buf[32];",
            f"    if (i2c_write_read(0x{info.i2c_addr:02X}, 0x00, buf, 32)"
            " == I2C_OK) {",
            "        /* TODO: Parse NMEA or UBX position data */",
            "    }",
            "}",
            "",
            "void gps_update_time(void) {",
            "    /* TODO: Sync OBC RTC from GPS time */",
            "}",
            "",
            "gps_position_t gps_get_position(void) {",
            "    return position;",
            "}",
            "",
        ])
    elif ss_id == "propulsion":
        lines.extend([
            "static float remaining_dv = 15.0f;  /* m/s */",
            "",
            "void prop_check_pressure(void) {",
            f"    uint8_t buf[2];",
            f"    if (i2c_write_read(0x{info.i2c_addr:02X}, 0x00, buf, 2)"
            " == I2C_OK) {",
            "        /* TODO: Parse tank pressure */",
            "    }",
            "}",
            "",
            "void prop_fire_thruster(uint16_t duration_ms) {",
            "    (void)duration_ms;",
            "    /* TODO: Open valve for specified duration */",
            "}",
            "",
            "void prop_shutdown(void) {",
            "    /* TODO: Close all valves, safe propulsion system */",
            "}",
            "",
            "float prop_get_remaining_dv(void) {",
            "    return remaining_dv;",
            "}",
            "",
        ])
    elif ss_id == "thermal":
        lines.extend([
            "static thermal_status_t status = {0};",
            "",
            "void thermal_read_temps(void) {",
            "    /* TODO: Read temperature sensors via ADC */",
            "}",
            "",
            "void thermal_control_heaters(void) {",
            "    for (int i = 0; i < 2; i++) {",
            "        if (status.zone_temp_c[i] < -10) {",
            "            status.heater_on[i] = true;",
            "            /* TODO: Enable heater GPIO */",
            "        } else if (status.zone_temp_c[i] > 5) {",
            "            status.heater_on[i] = false;",
            "            /* TODO: Disable heater GPIO */",
            "        }",
            "    }",
            "}",
            "",
            "thermal_status_t thermal_get_status(void) {",
            "    return status;",
            "}",
            "",
        ])

    return "\n".join(lines)


def _gen_payload_driver_h(design: CubeSatDesign) -> str:
    """Generate payload_driver.h -- payload interface."""
    guard = _header_guard("payload_driver.h")
    payload_type = design.payload_type

    lines = [
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f"/* Payload driver for {design.mission_name}",
        f" * Payload type: {payload_type}",
        " * Auto-generated by SAT-MAESTRO",
        f" * SPI CS: {SPI_CONFIG.get('payload_main', {}).get('cs_pin', 'N/A')}",
        " */",
        "",
        "#include <stdint.h>",
        "#include <stdbool.h>",
        "",
        f"#define PAYLOAD_POWER_W      {design.payload_power:.1f}",
        f"#define PAYLOAD_MASS_G       {design.payload_mass:.0f}",
        "",
        "void payload_init(void);",
        "void payload_shutdown(void);",
        "void payload_store_data(void);",
        "",
    ]

    if "Camera" in payload_type or "EO" in payload_type:
        lines.extend([
            "void payload_capture_image(void);",
            "uint32_t payload_get_image_count(void);",
        ])
    elif "SDR" in payload_type or "Comms" in payload_type:
        lines.extend([
            "void payload_sdr_sample(void);",
            "void payload_sdr_set_freq(uint32_t freq_hz);",
        ])
    elif "AIS" in payload_type:
        lines.extend([
            "void payload_ais_decode(void);",
            "uint32_t payload_ais_get_ship_count(void);",
        ])
    elif "IoT" in payload_type:
        lines.extend([
            "void payload_iot_poll(void);",
            "uint32_t payload_iot_get_msg_count(void);",
        ])
    else:
        lines.extend([
            "void payload_acquire(void);",
        ])

    lines.extend([
        "",
        f"#endif /* {guard} */",
        "",
    ])
    return "\n".join(lines)


def _gen_payload_driver_c(design: CubeSatDesign) -> str:
    """Generate payload_driver.c -- payload implementation stubs."""
    payload_type = design.payload_type

    lines = [
        f"/* Payload driver implementation ({payload_type})",
        " * Auto-generated by SAT-MAESTRO",
        " */",
        "",
        '#include "payload_driver.h"',
        '#include "spi_bus.h"',
        "",
        "static bool powered_on = false;",
        "static uint32_t data_count = 0;",
        "",
        "void payload_init(void) {",
        "    /* TODO: Configure payload power enable GPIO */",
        "    powered_on = true;",
        "}",
        "",
        "void payload_shutdown(void) {",
        "    /* TODO: Disable payload power */",
        "    powered_on = false;",
        "}",
        "",
        "void payload_store_data(void) {",
        "    /* TODO: Write acquired data to OBC flash storage */",
        "    data_count++;",
        "}",
        "",
    ]

    if "Camera" in payload_type or "EO" in payload_type:
        lines.extend([
            "void payload_capture_image(void) {",
            "    if (!powered_on) return;",
            "    /* TODO: Trigger image capture via SPI command */",
            "    /* TODO: Read image data from payload FIFO */",
            "}",
            "",
            "uint32_t payload_get_image_count(void) {",
            "    return data_count;",
            "}",
            "",
        ])
    elif "SDR" in payload_type or "Comms" in payload_type:
        lines.extend([
            "static uint32_t sdr_freq = 437000000;",
            "",
            "void payload_sdr_sample(void) {",
            "    if (!powered_on) return;",
            "    /* TODO: Trigger SDR I/Q sample capture */",
            "}",
            "",
            "void payload_sdr_set_freq(uint32_t freq_hz) {",
            "    sdr_freq = freq_hz;",
            "    /* TODO: Send frequency config to SDR via SPI */",
            "}",
            "",
        ])
    elif "AIS" in payload_type:
        lines.extend([
            "static uint32_t ship_count = 0;",
            "",
            "void payload_ais_decode(void) {",
            "    if (!powered_on) return;",
            "    /* TODO: Read AIS message buffer via SPI */",
            "    ship_count++;",
            "}",
            "",
            "uint32_t payload_ais_get_ship_count(void) {",
            "    return ship_count;",
            "}",
            "",
        ])
    elif "IoT" in payload_type:
        lines.extend([
            "static uint32_t msg_count = 0;",
            "",
            "void payload_iot_poll(void) {",
            "    if (!powered_on) return;",
            "    /* TODO: Poll IoT message queue via SPI */",
            "    msg_count++;",
            "}",
            "",
            "uint32_t payload_iot_get_msg_count(void) {",
            "    return msg_count;",
            "}",
            "",
        ])
    else:
        lines.extend([
            "void payload_acquire(void) {",
            "    if (!powered_on) return;",
            "    /* TODO: Acquire payload data */",
            "}",
            "",
        ])

    return "\n".join(lines)


def _gen_makefile(design: CubeSatDesign, c_files: list[str]) -> str:
    """Generate Makefile for ARM cross-compilation."""
    safe_name = _sanitize_name(design.mission_name)
    src_list = " \\\n\t".join(c_files)

    return "\n".join([
        f"# Makefile for {design.mission_name} OBC Firmware",
        "# Auto-generated by SAT-MAESTRO",
        "#",
        "# Target: STM32F4 (ARM Cortex-M4F)",
        "# Toolchain: arm-none-eabi-gcc",
        "",
        "# ---- Toolchain ----",
        "PREFIX  = arm-none-eabi-",
        "CC      = $(PREFIX)gcc",
        "AS      = $(PREFIX)as",
        "LD      = $(PREFIX)ld",
        "OBJCOPY = $(PREFIX)objcopy",
        "SIZE    = $(PREFIX)size",
        "",
        "# ---- Project ----",
        f"TARGET  = {safe_name.lower()}_fw",
        "",
        "# ---- Flags ----",
        "CPU     = -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16",
        "OPT     = -Os",
        "CFLAGS  = $(CPU) $(OPT) -Wall -Wextra -Werror -std=c11",
        "CFLAGS += -ffunction-sections -fdata-sections",
        "CFLAGS += -I.",
        "LDFLAGS = $(CPU) -T linker.ld -Wl,--gc-sections -nostartfiles",
        "LDFLAGS += -lnosys",
        "",
        "# ---- Sources ----",
        f"SRCS = {src_list}",
        "",
        "OBJS = $(SRCS:.c=.o)",
        "",
        "# ---- Rules ----",
        "",
        "all: $(TARGET).elf $(TARGET).bin size",
        "",
        "$(TARGET).elf: $(OBJS)",
        "\t$(CC) $(LDFLAGS) -o $@ $^",
        "",
        "$(TARGET).bin: $(TARGET).elf",
        "\t$(OBJCOPY) -O binary $< $@",
        "",
        "$(TARGET).hex: $(TARGET).elf",
        "\t$(OBJCOPY) -O ihex $< $@",
        "",
        "%.o: %.c",
        "\t$(CC) $(CFLAGS) -c -o $@ $<",
        "",
        "size: $(TARGET).elf",
        "\t$(SIZE) $<",
        "",
        "flash: $(TARGET).bin",
        "\tst-flash write $< 0x08000000",
        "",
        "clean:",
        "\trm -f $(OBJS) $(TARGET).elf $(TARGET).bin $(TARGET).hex",
        "",
        ".PHONY: all clean flash size",
        "",
    ])


def _gen_linker_ld() -> str:
    """Generate a minimal linker script for STM32F4."""
    return "\n".join([
        "/* Linker script for STM32F4 (512K Flash, 128K SRAM)",
        " * Auto-generated by SAT-MAESTRO",
        " *",
        " * TODO: Adjust FLASH/RAM sizes to match actual MCU variant.",
        " */",
        "",
        "MEMORY",
        "{",
        "    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K",
        "    SRAM  (rwx) : ORIGIN = 0x20000000, LENGTH = 128K",
        "}",
        "",
        "_estack = ORIGIN(SRAM) + LENGTH(SRAM);",
        "",
        "SECTIONS",
        "{",
        "    .text : {",
        "        KEEP(*(.isr_vector))",
        "        *(.text*)",
        "        *(.rodata*)",
        "        . = ALIGN(4);",
        "        _etext = .;",
        "    } > FLASH",
        "",
        "    .data : AT(_etext) {",
        "        _sdata = .;",
        "        *(.data*)",
        "        . = ALIGN(4);",
        "        _edata = .;",
        "    } > SRAM",
        "",
        "    .bss : {",
        "        _sbss = .;",
        "        *(.bss*)",
        "        *(COMMON)",
        "        . = ALIGN(4);",
        "        _ebss = .;",
        "    } > SRAM",
        "",
        "    /DISCARD/ : {",
        "        *(.ARM.exidx*)",
        "        *(.ARM.attributes*)",
        "    }",
        "}",
        "",
    ])


def _gen_readme(
    design: CubeSatDesign,
    subs: list[_SubsystemInfo],
    result: FirmwareResult,
) -> str:
    """Generate README.md with build and flash instructions."""
    subsystem_names = [s.name for s in subs]
    safe_name = _sanitize_name(design.mission_name).lower()

    lines = [
        f"# {design.mission_name} OBC Firmware",
        "",
        f"Auto-generated skeleton firmware by **SAT-MAESTRO** for the "
        f"{design.mission_name} {design.sat_size} CubeSat.",
        "",
        "## Subsystems",
        "",
    ]
    for s in subs:
        bus_info_parts: list[str] = []
        if s.has_i2c:
            bus_info_parts.append(f"I2C 0x{s.i2c_addr:02X}" if s.i2c_addr else "I2C")
        if s.has_uart:
            bus_info_parts.append(f"UART {s.uart_baud} baud" if s.uart_baud else "UART")
        if s.has_spi:
            bus_info_parts.append(f"SPI CS={s.spi_cs_pin}" if s.spi_cs_pin else "SPI")
        bus_str = ", ".join(bus_info_parts) if bus_info_parts else "power only"
        lines.append(f"- **{s.name}** ({bus_str})")

    lines.append(f"- **Payload** ({design.payload_type}, SPI)")
    lines.append("")
    lines.append("## Prerequisites")
    lines.append("")
    lines.append("- ARM GCC toolchain (`arm-none-eabi-gcc`)")
    lines.append("- `st-flash` from stlink tools (for flashing)")
    lines.append("- GNU Make")
    lines.append("")
    lines.append("## Build")
    lines.append("")
    lines.append("```bash")
    lines.append("make clean && make all")
    lines.append("```")
    lines.append("")
    lines.append("## Flash")
    lines.append("")
    lines.append("Connect STM32 via ST-Link programmer and run:")
    lines.append("")
    lines.append("```bash")
    lines.append("make flash")
    lines.append("```")
    lines.append("")
    lines.append(f"This writes `{safe_name}_fw.bin` to address `0x08000000`.")
    lines.append("")
    lines.append("## File Structure")
    lines.append("")
    for f in result.files:
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Important Notes")
    lines.append("")
    lines.append("1. **This is skeleton code.** All hardware register access is "
                 "stubbed with TODO comments.")
    lines.append("2. Replace stubs with STM32 HAL or direct register writes "
                 "before flight.")
    lines.append("3. The linker script (`linker.ld`) assumes STM32F4 with 512K "
                 "Flash / 128K SRAM. Adjust for your MCU variant.")
    lines.append("4. Add a startup file (`startup_stm32f4xx.s`) with the vector "
                 "table and Reset_Handler before compiling.")
    lines.append("5. The scheduler is a simple cooperative round-robin. Consider "
                 "FreeRTOS for preemptive multitasking.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------

class FirmwareGenerator:
    """Generate skeleton firmware C source files for a CubeSat OBC.

    Produces a complete, compilable (with stubs) firmware project directory
    based on the CubeSat design parameters. Generated code reflects the
    actual selected subsystems, bus configurations, I2C addresses, UART
    baud rates, and SPI chip selects.

    Args:
        design: The CubeSat design from the wizard questionnaire.
    """

    def __init__(self, design: CubeSatDesign) -> None:
        self._design = design
        self._subs = _resolve_subsystem_info(design)

    def generate(self, output_dir: Path) -> FirmwareResult:
        """Generate all firmware source files into the output directory.

        Creates the output directory if it does not exist. Overwrites any
        existing files with the same names.

        Args:
            output_dir: Target directory for generated source files.

        Returns:
            FirmwareResult with list of generated files and line counts.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        result = FirmwareResult()
        total_lines = 0

        # Collect all .c files for the Makefile
        c_files: list[str] = []

        # -- Core files (always generated) --
        file_map: dict[str, str] = {}

        file_map["obc_main.c"] = _gen_obc_main(self._design, self._subs)
        c_files.append("obc_main.c")

        file_map["hal.h"] = _gen_hal_h(self._design, self._subs)
        file_map["hal.c"] = _gen_hal_c(self._design)
        c_files.append("hal.c")

        file_map["scheduler.h"] = _gen_scheduler_h()
        file_map["scheduler.c"] = _gen_scheduler_c()
        c_files.append("scheduler.c")

        # -- Bus drivers (conditional) --
        has_i2c = any(s.has_i2c for s in self._subs)
        has_uart = any(s.has_uart for s in self._subs)
        has_spi = any(s.has_spi for s in self._subs)

        if has_i2c:
            file_map["i2c_bus.h"] = _gen_i2c_h()
            file_map["i2c_bus.c"] = _gen_i2c_c()
            c_files.append("i2c_bus.c")

        if has_uart:
            file_map["uart_bus.h"] = _gen_uart_h()
            file_map["uart_bus.c"] = _gen_uart_c()
            c_files.append("uart_bus.c")

        if has_spi:
            file_map["spi_bus.h"] = _gen_spi_h()
            file_map["spi_bus.c"] = _gen_spi_c()
            c_files.append("spi_bus.c")

        # -- Subsystem drivers --
        for sub in self._subs:
            if sub.id == "obc":
                continue  # OBC is the main firmware itself

            if sub.id == "eps":
                file_map["eps_driver.h"] = _gen_eps_driver_h(self._design)
                file_map["eps_driver.c"] = _gen_eps_driver_c()
                c_files.append("eps_driver.c")
            else:
                h_name = f"{sub.id}_driver.h"
                c_name = f"{sub.id}_driver.c"
                file_map[h_name] = _gen_subsystem_driver_h(
                    sub.id, sub, self._design
                )
                file_map[c_name] = _gen_subsystem_driver_c(sub.id, sub)
                c_files.append(c_name)

        # -- Payload driver (always generated) --
        file_map["payload_driver.h"] = _gen_payload_driver_h(self._design)
        file_map["payload_driver.c"] = _gen_payload_driver_c(self._design)
        c_files.append("payload_driver.c")

        # -- Build files --
        file_map["Makefile"] = _gen_makefile(self._design, c_files)
        file_map["linker.ld"] = _gen_linker_ld()

        # -- Write all files --
        for filename, content in file_map.items():
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            line_count = content.count("\n")
            total_lines += line_count
            result.files.append(filename)
            logger.debug("Generated %s (%d lines)", filename, line_count)

        # -- README (needs result.files populated first) --
        result.main_file = "obc_main.c"
        result.total_lines = total_lines

        readme_content = _gen_readme(self._design, self._subs, result)
        readme_path = output_dir / "README.md"
        readme_path.write_text(readme_content, encoding="utf-8")
        readme_lines = readme_content.count("\n")
        total_lines += readme_lines
        result.files.append("README.md")
        result.total_lines = total_lines

        logger.info(
            "Firmware generation complete: %d files, %d total lines in %s",
            result.file_count,
            result.total_lines,
            output_dir,
        )

        return result
