# gnome-terminal-restore -- bash hook
#
# Records this tab's working directory and active Python environment so that
# gt-save can capture them. This exists because /proc/<pid>/environ is a
# snapshot of the environment at exec time: a virtualenv activated inside an
# already-running shell is invisible there, which is the normal case.
#
# Sourced from ~/.bashrc by install.sh. Safe to source more than once.

__gtr_live_dir() {
    if [ -n "${GTR_DATA_DIR:-}" ]; then
        printf '%s/live\n' "$GTR_DATA_DIR"
    else
        printf '%s/gnome-terminal-restore/live\n' "${XDG_DATA_HOME:-$HOME/.local/share}"
    fi
}

__gtr_record() {
    local __gtr_status=$?          # preserve $? for anything else on PROMPT_COMMAND
    if [ -n "${GNOME_TERMINAL_SCREEN:-}" ]; then
        local __gtr_dir
        __gtr_dir=$(__gtr_live_dir)
        [ -d "$__gtr_dir" ] || mkdir -p "$__gtr_dir" 2>/dev/null
        printf '%s\t%s\t%s\t%s\n' \
            "$PWD" "${VIRTUAL_ENV:-}" "${CONDA_DEFAULT_ENV:-}" "${CONDA_PREFIX:-}" \
            > "$__gtr_dir/$$" 2>/dev/null
    fi
    return $__gtr_status
}

# bash 5.1+ allows PROMPT_COMMAND to be an array; handle both forms, and never
# register twice if this file is sourced again.
if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
    if [[ " ${PROMPT_COMMAND[*]} " != *" __gtr_record "* ]]; then
        PROMPT_COMMAND+=(__gtr_record)
    fi
elif [[ ";${PROMPT_COMMAND};" != *";__gtr_record;"* ]]; then
    PROMPT_COMMAND="__gtr_record${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
