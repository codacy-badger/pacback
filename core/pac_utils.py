#! /usr/bin/env python3
# Utils used by pacback
import os
import re
import itertools
import sys
import datetime as dt
import multiprocessing as mp
import python_scripts as PS


#<#><#><#><#><#><#>#<#>#<#
#+# Pacman Utils
#<#><#><#><#><#><#>#<#>#<#


def pacman_Q(replace_spaces=False):
    '''Writes the output into /tmp, reads file, then removes file.'''
    os.system("pacman -Q > /tmp/pacman_q.meta")
    ql = PS.Read_List('/tmp/pacman_q.meta', typ='set')
    PS.RM_File('/tmp/pacman_q.meta', sudo=True)
    if replace_spaces is True:
        rl = {s.strip().replace(' ', '-') for s in ql}
        return rl
    else:
        return ql


def first_pkg_path(pkg, fs_list):
    '''Used by parallel pac_cache filter. Not General Purpose'''
    for f in fs_list:
        if f.split('/')[-1] == pkg:
            return f


def fetch_paccache(pac_path=None):
    '''Always returns a unique list of pkgs found on the file sys.'''
    # Search File System
    pac_cache = PS.Search_FS('/var/cache/pacman/pkg', 'set')
    user_cache = {f for f in PS.Search_FS('~/.cache', 'set') if f.endswith(".pkg.tar.xz") or f.endswith(".pkg.tar.zst")}

    if pac_path is not None:
        # Find package versions stored in pacback rps
        pacback_cache = {f for f in PS.Search_FS(pac_path, 'set') if f.endswith('.pkg.tar.xz') or f.endswith(".pkg.tar.zst")}
        fs_list = pac_cache.union(user_cache, pacback_cache)
    else:
        fs_list = pac_cache.union(user_cache)

    unique_pkgs = PS.Trim_Dir(fs_list)
    if len(fs_list) != len(unique_pkgs):
        PS.prWorking('Filtering Duplicate Packages...')
        # Should usually only run when a pac_path is defined and full rp's are present
        # This pool returns the first instance of a file matching a package name
        # Some locking happens but this reduces filter times by ~75%-200%
        with mp.Pool(processes=4) as pool:
            new_fs = pool.starmap(first_pkg_path, zip(unique_pkgs, itertools.repeat(fs_list)))
        return new_fs

    else:
        return fs_list


def search_paccache(pkg_list, fs_list):
    '''Searches cache for matching pkg versions and returns results.'''
    # Combing package names into one term provides much faster results
    bulk_search = re.compile('|'.join(list(re.escape(pkg) for pkg in pkg_list)))
    found_pkgs = set()
    for f in fs_list:
        if re.findall(bulk_search, f.lower()):
            found_pkgs.add(f)
    return found_pkgs


def trim_pkg_list(pkg_list):
    '''Removes prefix dir and x86_64.pkg.tar.zsd suffix.'''
    pkg_split = {pkg.split('/')[-1] for pkg in pkg_list}
    pkg_split = {'-'.join(pkg.split('-')[:-1]) for pkg in pkg_split}
    return pkg_split


#<#><#><#><#><#><#>#<#>#<#
#+# Single Package Search
#<#><#><#><#><#><#>#<#>#<#


def user_pkg_search(search_pkg, cache):
    '''Provides more accurate searches for single pkg names without a version.'''
    pkgs = trim_pkg_list(cache)
    found = set()

    for p in pkgs:
        r = re.split("\d+-\d+|\d+(?:\.\d+)+|\d:\d+(?:\.\d+)+", p)[0]
        if r.strip()[-1] == '-':
            x = r.strip()[:-1]
        else:
            x = r
        if re.fullmatch(re.escape(search_pkg.lower().strip()), x):
            found.add(p)

    if len(found) == 0:
        PS.prError('No Packages Found!')
        if PS.YN_Frame('Do You Want to Extend the Regex Search?') is True:
            for p in pkgs:
                if re.findall(re.escape(search_pkg.lower().strip()), p):
                    found.add(p)
    return found


#<#><#><#><#><#><#>#<#>#<#
#+# Rollback Packages
#<#><#><#><#><#><#>#<#>#<#


def rollback_packages(pkg_list):
    PS.prWorking('Searching File System for Packages...')
    cache = PS.fetch_paccache(base_dir + '/restore-points')
    for pkg in pkg_list:
        found_pkgs = PU.user_pkg_search(pkg, cache)
        if len(found_pkgs) > 0:
            PS.prSuccess('Pacback Found the Following Package Versions for ' + pkg + ':')
            answer = PS.Multi_Choice_Frame(found_pkgs)
            if answer is False:
                break
            for x in cache:
                if re.findall(re.escape(answer), x):
                    path = x
            os.system('sudo pacman -U ' + path)
        else:
            PS.prError('No Packages Found Under the Name: ' + pkg)


#<#><#><#><#><#><#>#<#>#<#
#+# Better Cache Cleaning
#<#><#><#><#><#><#>#<#>#<#


def clean_cache(count, base_dir):
    PS.prWorking('Starting Advanced Cache Cleaning...')
    if PS.YN_Frame('Do You Want To Uninstall Orphaned Packages?') is True:
        os.system('sudo pacman -R $(pacman -Qtdq)')

    if PS.YN_Frame('Do You Want To Remove Old Versions of Installed Packages?') is True:
        os.system('sudo paccache -rk ' + count)

    if PS.YN_Frame('Do You Want To Remove Cached Orphans?') is True:
        os.system('sudo paccache -ruk0')

    if PS.YN_Frame('Do You Want To Check For Old Pacback Restore Points?') is True:
        rps = {f for f in PS.Search_FS(base_dir + '/restore-points', 'set') if f.endswith(".meta")}

        for m in rps:
            # Find RP Create Date in Meta File
            meta = PS.Read_List(m)
            for l in meta:
                if l.split(':')[0] == 'Date Created':
                    target_date = l.split(':')[1].strip()
                    break

            # Parse and Format Dates for Compare
            today = dt.datetime.now().strftime("%Y/%m/%d")
            t_split = list(today.split('/'))
            today_date = dt.date(int(t_split[0]), int(t_split[1]), int(t_split[2]))
            o_split = list(target_date.split('/'))
            old_date = dt.date(int(o_split[0]), int(o_split[1]), int(o_split[2]))

            # Compare Days
            days = (today_date - old_date).days
            if days > 180:
                PS.prWarning(m.split('/')[-1] + ' Is Over 180 Days Old!')
                if PS.YN_Frame('Do You Want to Remove This Restore Point?') is True:
                    PS.RM_File(m, sudo=True)
                    PS.RM_Dir(m[:-5], sudo=True)
                    PS.prSuccess('Restore Point Removed!')
            PS.prSuccess(m.split('/')[-1] + ' Is Only ' + str(days) + ' Days Old!')


#<#><#><#><#><#><#>#<#>#<#
#+# Unlock Mirrorlist
#<#><#><#><#><#><#>#<#>#<#


def unlock_rollback():
    # Check if mirrorlist is locked
    if len(PS.Read_List('/etc/pacman.d/mirrorlist')) == 1:
        if os.path.exists('/etc/pacman.d/mirrolist.pacback'):
            list_fetch = PS.YN_Frame('Pacback Can\'t Find Your Backup Mirrorlist! Do You Want to Fetch a New US HTTPS Mirrorlist?')
            if list_fetch is True:
                os.system("curl -s 'https://www.archlinux.org/mirrorlist/?country=US&protocol=https&use_mirror_status=on' | sed -e 's/^#Server/Server/' -e '/^#/d' | sudo tee /etc/pacman.d/mirrorlist.pacback >/dev/null")
            else:
                sys.exit('Critical Error! Please Manually Replace Your Mirrorlist!')
        os.system('sudo cp /etc/pacman.d/mirrorlist.pacback /etc/pacman.d/mirrorlist')
    else:
        return PS.prError('Pacback Does NOT Have an Active Date Lock!')

    # Update?
    update = PS.YN_Frame('Do You Want to Update Your System Now?')
    if update is True:
        os.system('sudo pacman -Syu')
    if update is False:
        return print('Skipping Update!')


#<#><#><#><#><#><#>#<#>#<#
#+# Pacman Hook
#<#><#><#><#><#><#>#<#>#<#


def pacback_hook(install):
    '''Installs or removes a standard alpm hook in /etc/pacman.d/hooks
    Runs as a PreTransaction hook during every upgrade.'''
    if install is True:
        PS.MK_Dir('/etc/pacman.d/hooks', sudo=True)
        PS.Uncomment_Line_Sed('HookDir', '/etc/pacman.conf', sudo=True)
        if not os.path.exists('/etc/pacman.d/hooks/pacback.hook'):
            hook = ['[Trigger]',
                    'Operation = Upgrade',
                    'Type = Package',
                    'Target = *',
                    '',
                    '[Action]',
                    'Description = Pre-Upgrade Pacback Hook',
                    'Depends = pacman',
                    'When = PreTransaction',
                    'Exec = /usr/bin/pacback --hook']
            for h in hook:
                os.system('echo ' + PS.Escape_Bash(h) + '| sudo tee -a /etc/pacman.d/hooks/pacback.hook > /dev/null')
            PS.prSuccess('Pacback Hook is Now Installed!')
        else:
            PS.prSuccess('Pacback Hook is Already Installed!')

    elif install is False:
        PS.RM_File('/etc/pacman.d/hooks/pacback.hook', sudo=True)
        PS.prSuccess('Pacback Hook Removed!')
