cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(ods_optical_capture C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(ods-optical-capture capture.c)
target_compile_options(ods-optical-capture PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(ods-optical-capture PRIVATE
    PICO_STDIO_DEFAULT_CRLF=0 PICO_STDIO_USB_DEFAULT_CRLF=0
    PICO_STDIO_USB_STDOUT_TIMEOUT_US=2000000)
target_link_libraries(ods-optical-capture pico_stdlib hardware_adc hardware_dma hardware_clocks)
pico_enable_stdio_usb(ods-optical-capture 1)
pico_enable_stdio_uart(ods-optical-capture 0)
pico_add_extra_outputs(ods-optical-capture)
