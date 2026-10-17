# bash completion for gfp
# Source this file or place it in /etc/bash_completion.d/ or ~/.local/share/bash-completion/completions/gfp

_gfp() {
    local cur prev words cword
    _init_completion || return

    local commands="status add commit diff log pull push checkout stash show clean blame branch switch clone reopen completion restore resolve rebase st ci co br di sw"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    local command="${words[1]}"
    case "$command" in
        status|st)
            COMPREPLY=( $(compgen -W "-c --cl --pending -h --help" -- "$cur") )
            ;;
        add)
            case "$prev" in
                *)
                    COMPREPLY=( $(compgen -W "-A --all -u --update -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        commit|ci)
            case "$prev" in
                -m|--message)
                    return 0
                    ;;
                -c|--cl)
                    local cls=$(p4 changes -s pending 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-m --message -a --all --amend -c --cl -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        diff|di)
            case "$prev" in
                -c|--cl)
                    local cls=$(p4 changes -m 30 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-c --cl --stat --color --no-color -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        log)
            case "$prev" in
                -n|--max-count|-u|--user|--author)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-n --max-count -a --all --oneline -p --patch -u --user --author -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        restore)
            case "$prev" in
                -c|--cl)
                    local cls=$(p4 changes -s pending 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-k --keep -s --staged -c --cl -f --force -W --worktree -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        resolve)
            COMPREPLY=( $(compgen -W "--ours --theirs --am -n --dry-run -h --help" -- "$cur") $(compgen -f -- "$cur") )
            ;;
        rebase)
            case "$prev" in
                -s|--squash|--onto)
                    local cls=$(p4 changes -s pending 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                -m|--message)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-s --squash --onto -i --interactive -m --message -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        pull)
            COMPREPLY=( $(compgen -W "-f --force -n --dry-run -h --help" -- "$cur") $(compgen -f -- "$cur") )
            ;;
        push)
            case "$prev" in
                -c|--cl)
                    local cls=$(p4 changes -s pending 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-f --force -n --dry-run -c --cl --gated -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        checkout|co)
            COMPREPLY=( $(compgen -W "-f --force -h --help" -- "$cur") $(compgen -f -- "$cur") )
            ;;
        stash)
            case "$prev" in
                -c|--cl)
                    local cls=$(p4 changes -s shelved 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    local actions="save pop list drop show"
                    COMPREPLY=( $(compgen -W "$actions -m --message -c --cl -k --keep -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        show)
            case "$prev" in
                *)
                    local cls=$(p4 changes -m 30 -s submitted 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls --stat -s -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        clean)
            COMPREPLY=( $(compgen -W "-f --force -n --dry-run -d -h --help" -- "$cur") $(compgen -f -- "$cur") )
            ;;
        blame)
            case "$prev" in
                -c|--cl|--rev|-L|--line-range)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-c --cl --rev -u --user -d --date -L --line-range -q --quiet -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        branch|br)
            case "$prev" in
                -t|--type)
                    COMPREPLY=( $(compgen -W "development release mainline virtual task" -- "$cur") )
                    ;;
                -P|--parent)
                    local streams=$(p4 streams 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$streams" -- "$cur") )
                    ;;
                *)
                    local streams=$(p4 streams 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$streams -a --all -d --delete -P --parent -t --type -v --verbose -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        switch|sw)
            case "$prev" in
                -t|--type)
                    COMPREPLY=( $(compgen -W "development release mainline virtual task" -- "$cur") )
                    ;;
                -P|--parent)
                    local streams=$(p4 streams 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$streams" -- "$cur") )
                    ;;
                *)
                    local streams=$(p4 streams 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$streams -c --create -l --list -P --parent -t --type -s --stash -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        clone)
            case "$prev" in
                -c|--client|-d|--dir)
                    return 0
                    ;;
                *)
                    local streams=$(p4 streams 2>/dev/null | awk '{print $2}')
                    local depots=$(p4 depots 2>/dev/null | awk '{print "//"$2"/..."}')
                    COMPREPLY=( $(compgen -W "$streams $depots -c --client -d --dir -h --help" -- "$cur") )
                    ;;
            esac
            ;;
        reopen)
            case "$prev" in
                -c|--cl)
                    local cls="default "$(p4 changes -s pending 2>/dev/null | awk '{print $2}')
                    COMPREPLY=( $(compgen -W "$cls" -- "$cur") )
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-c --cl -h --help" -- "$cur") $(compgen -f -- "$cur") )
                    ;;
            esac
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh tcsh" -- "$cur") )
            ;;
        *)
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
            ;;
    esac
}

complete -F _gfp gfp
