/*
 * Small native entrypoint for gg-gui.
 *
 * It embeds the system CPython and runs the compiled GUI bytecode.  This keeps
 * the process a real ELF binary while the GTK/PyGObject UI and the allowlisted
 * Python core stay unchanged.
 *
 * Build with:
 *   gcc -O2 -o gg-gui-bin launcher.c $(python3-config --embed --cflags --ldflags)
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s script [args...]\n", argv[0]);
        return 2;
    }

    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.parse_argv = 0;

    PyStatus status = PyConfig_SetBytesString(
        &config, &config.program_name, "/usr/bin/python3");
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        Py_ExitStatusException(status);
    }

    status = PyConfig_SetBytesArgv(&config, argc - 1, argv + 1);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        Py_ExitStatusException(status);
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        Py_ExitStatusException(status);
    }

    const char *script = argv[1];
    FILE *fp = fopen(script, "rb");
    if (fp == NULL) {
        perror(script);
        Py_FinalizeEx();
        return 1;
    }

    int rc = PyRun_SimpleFileExFlags(fp, script, 1, NULL);
    if (Py_FinalizeEx() < 0) {
        rc = 120;
    }
    return rc == 0 ? 0 : 1;
}
