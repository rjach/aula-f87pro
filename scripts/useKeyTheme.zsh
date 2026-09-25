# useKeyTheme -- drive the Aula F87 Pro lighting from the shell.
#
# Install by sourcing this file from ~/.zshrc:
#     source ~/Stuffs/ooo/aula-f87pro/scripts/useKeyTheme.zsh
#
# Usage:
#     useKeyTheme                      # (re)start the current theme, reactive
#     useKeyTheme --theme=nebula       # switch theme and remember it
#     useKeyTheme --list               # list available themes
#     useKeyTheme --status             # what is running right now
#     useKeyTheme --stop               # stop, leaving the lights as they are
#     useKeyTheme --off                # stop and turn the lights off
#
# The board keeps no lighting state of its own, so a background process has to
# stay alive for the theme to remain visible. This starts exactly one, replacing
# any previous instance.

# Where the project lives. Override before sourcing if you move it.
: ${AULA_F87_HOME:="$HOME/Stuffs/ooo/aula-f87pro"}

# The theme that survives between shells is remembered here.
: ${AULA_F87_STATE_DIR:="${XDG_STATE_HOME:-$HOME/.local/state}/aula-f87pro"}

: ${AULA_F87_DEFAULT_THEME:="flow"}
: ${AULA_F87_DEFAULT_BRIGHTNESS:=100}

_aula_f87_bin()       { print -r -- "$AULA_F87_HOME/.venv/bin/aula-f87pro" }

# Theme names only: the listing's indented rows, not its footer lines.
_aula_f87_themes() {
    "$(_aula_f87_bin)" --list-themes 2>/dev/null | awk '/^  [a-z]/ {print $1}'
}
_aula_f87_pidfile()   { print -r -- "$AULA_F87_STATE_DIR/theme.pid" }
_aula_f87_themefile() { print -r -- "$AULA_F87_STATE_DIR/current-theme" }
_aula_f87_logfile()   { print -r -- "$AULA_F87_STATE_DIR/theme.log" }

# The remembered theme, falling back to the default.
_aula_f87_current_theme() {
    local file="$(_aula_f87_themefile)"
    if [[ -r "$file" ]]; then
        local saved="$(<"$file")"
        [[ -n "$saved" ]] && { print -r -- "$saved"; return }
    fi
    print -r -- "$AULA_F87_DEFAULT_THEME"
}

# PID of the running instance, or nothing if it is not running.
_aula_f87_running_pid() {
    local file="$(_aula_f87_pidfile)" pid
    [[ -r "$file" ]] || return 1
    pid="$(<"$file")"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && { print -r -- "$pid"; return 0 }
    return 1
}

_aula_f87_stop() {
    local pid
    if pid="$(_aula_f87_running_pid)"; then
        kill "$pid" 2>/dev/null
        # Give it a moment to release the HID handle before anything reopens it.
        local waited=0
        while kill -0 "$pid" 2>/dev/null && (( waited < 20 )); do
            sleep 0.05
            (( waited++ ))
        done
        kill -9 "$pid" 2>/dev/null
    fi
    # Catch any stray instance started outside this function.
    pkill -f "aula-f87pro --theme" 2>/dev/null
    rm -f "$(_aula_f87_pidfile)"
    return 0
}

useKeyTheme() {
    local bin="$(_aula_f87_bin)"
    local theme="" brightness="$AULA_F87_DEFAULT_BRIGHTNESS"
    local reactive=1 action="start" arg

    for arg in "$@"; do
        case "$arg" in
            --theme=*)      theme="${arg#--theme=}" ;;
            --brightness=*) brightness="${arg#--brightness=}" ;;
            --no-reactive)  reactive=0 ;;
            --list|-l)      action="list" ;;
            --status|-s)    action="status" ;;
            --stop)         action="stop" ;;
            --off)          action="off" ;;
            --help|-h)      action="help" ;;
            *)
                print -u2 "useKeyTheme: unknown option '$arg' (try --help)"
                return 2
                ;;
        esac
    done

    if [[ ! -x "$bin" ]]; then
        print -u2 "useKeyTheme: cannot find $bin"
        print -u2 "  Set AULA_F87_HOME to the project directory, or run: uv pip install -e ."
        return 1
    fi

    case "$action" in
        help)
            print "useKeyTheme [--theme=NAME] [--brightness=1-100] [--no-reactive]"
            print "useKeyTheme --list | --status | --stop | --off"
            print ""
            print "With no arguments it restarts the current theme ($(_aula_f87_current_theme)) in reactive mode."
            return 0
            ;;
        list)
            "$bin" --list-themes
            print ""
            print "Current: $(_aula_f87_current_theme)"
            return 0
            ;;
        status)
            local pid
            if pid="$(_aula_f87_running_pid)"; then
                print "running: $(_aula_f87_current_theme) (pid $pid)"
            else
                print "not running (current theme: $(_aula_f87_current_theme))"
            fi
            return 0
            ;;
        stop)
            _aula_f87_stop
            print "stopped"
            return 0
            ;;
        off)
            _aula_f87_stop
            "$bin" --off >/dev/null 2>&1
            print "lights off"
            return 0
            ;;
    esac

    # No --theme given: keep using whatever is current.
    [[ -z "$theme" ]] && theme="$(_aula_f87_current_theme)"

    if ! _aula_f87_themes | grep -qx -- "$theme"; then
        print -u2 "useKeyTheme: unknown theme '$theme'"
        print -u2 "  Available: $(_aula_f87_themes | tr '\n' ' ')"
        return 2
    fi

    mkdir -p "$AULA_F87_STATE_DIR"
    _aula_f87_stop

    local -a cmd
    cmd=("$bin" --theme "$theme" --brightness "$brightness" --duration 0)
    (( reactive )) && cmd+=(--reactive)

    nohup "${cmd[@]}" >"$(_aula_f87_logfile)" 2>&1 &
    local pid=$!
    disown 2>/dev/null

    print -r -- "$pid" > "$(_aula_f87_pidfile)"
    print -r -- "$theme" > "$(_aula_f87_themefile)"

    # The process exits immediately if the device cannot be opened, so confirm
    # it is actually alive rather than reporting a success that did not happen.
    sleep 1.5
    if ! kill -0 "$pid" 2>/dev/null; then
        print -u2 "useKeyTheme: failed to start"
        sed 's/^/  /' "$(_aula_f87_logfile)" >&2
        rm -f "$(_aula_f87_pidfile)"
        return 1
    fi

    if (( reactive )); then
        print "$theme + bubbles running (pid $pid)"
    else
        print "$theme running (pid $pid)"
    fi
}

# Tab-completion for theme names, read from the CLI so it cannot go stale.
_useKeyTheme() {
    local -a themes
    themes=(${(f)"$(_aula_f87_themes)"})
    _arguments \
        "--theme=[theme to run]:theme:(${themes})" \
        '--brightness=[brightness 1-100]:brightness:' \
        '--no-reactive[no keystroke bubbles]' \
        '--list[list themes]' \
        '--status[show what is running]' \
        '--stop[stop the running theme]' \
        '--off[stop and turn lights off]' \
        '--help[show usage]'
}
compdef _useKeyTheme useKeyTheme 2>/dev/null
