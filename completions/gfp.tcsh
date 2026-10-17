# tcsh completion for gfp
# Source this file in your ~/.cshrc or ~/.tcshrc:
#   source /path/to/gfp/completions/gfp.tcsh

set gfp_cmds = (status add commit diff log pull push checkout stash show clean blame branch switch clone reopen restore resolve rebase completion st ci co br di sw)
set gfp_stream_types = (development release mainline virtual task)
set gfp_stash_actions = (save pop list drop show)
set gfp_shells = (bash zsh tcsh)

complete gfp \
    'p/1/$gfp_cmds/' \
    'n/status/(-c --cl --pending -h --help)/' \
    'n/st/(-c --cl --pending -h --help)/' \
    'n/commit/(-m --message -a --all --amend -c --cl -h --help)/' \
    'n/ci/(-m --message -a --all --amend -c --cl -h --help)/' \
    'n/diff/(-c --cl --stat --color --no-color -h --help)/' \
    'n/di/(-c --cl --stat --color --no-color -h --help)/' \
    'n/rebase/(-s --squash --onto -i --interactive -m --message -h --help)/' \
    'n/restore/(-k --keep -s --staged -c --cl -f --force -W --worktree -h --help)/' \
    'n/push/(-f --force -n --dry-run -c --cl --gated -h --help)/' \
    'n/pull/(-f --force -n --dry-run -h --help)/' \
    'n/switch/(-c --create -l --list -P --parent -t --type -s --stash -h --help)/' \
    'n/sw/(-c --create -l --list -P --parent -t --type -s --stash -h --help)/' \
    'n/branch/(-a --all -d --delete -P --parent -t --type -v --verbose -h --help)/' \
    'n/br/(-a --all -d --delete -P --parent -t --type -v --verbose -h --help)/' \
    'n/stash/(save pop list drop show -m --message -c --cl -k --keep -h --help)/' \
    'n/clean/(-f --force -n --dry-run -d -h --help)/' \
    'n/blame/(-c --cl --rev -u --user -d --date -L --line-range -q --quiet -h --help)/' \
    'n/log/(-n --max-count -a --all --oneline -p --patch -u --user --author -h --help)/' \
    'n/resolve/(--ours --theirs --am -n --dry-run -h --help)/' \
    'n/checkout/(-f --force -h --help)/' \
    'n/co/(-f --force -h --help)/' \
    'n/add/(-A --all -u --update -h --help)/' \
    'n/clone/(-c --client -d --dir -h --help)/' \
    'n/reopen/(-c --cl -h --help)/' \
    'n/show/(-s --stat -h --help)/' \
    'n/completion/$gfp_shells/' \
    'n/stash/$gfp_stash_actions/' \
    'n/-t/$gfp_stream_types/' \
    'n/--type/$gfp_stream_types/' \
    'n/-P/`p4 streams |& awk "/Stream/ {print \$2}"`/' \
    'n/--parent/`p4 streams |& awk "/Stream/ {print \$2}"`/' \
    'n/-s/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'n/--squash/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'n/--onto/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'n/-c/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'n/--cl/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'c/-c/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'c/--cl/`p4 changes -s pending |& awk "/Change/ {print \$2}"`/' \
    'n/-d/d/' \
    'n/--dir/d/' \
    'N/branch/`p4 streams |& awk "/Stream/ {print \$2}"`/' \
    'N/switch/`p4 streams |& awk "/Stream/ {print \$2}"`/' \
    'N/clone/`p4 streams |& awk "/Stream/ {print \$2}"`/'
