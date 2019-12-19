#! /usr/bin/env python3
#### A utility for marking and restoring stable arch packages
version = '1.5.3'
from python_scripts import *
from pac_utils import *
import tqdm, argparse

#<#><#><#><#><#><#>#<#>#<#
#+# Create Restore Point
#<#><#><#><#><#><#>#<#>#<#

def create_restore_point(rp_num, rp_full, dir_list):
    ### Fail Safe for New Users
    if not os.path.exists(base_dir + '/restore-points'):
        MK_Dir(base_dir + '/restore-points', sudo=True)
        Open_Permissions(base_dir + '/restore-points')

    ### Set Base Vars
    rp_path = base_dir + '/restore-points/rp' + str(rp_num).zfill(2)
    rp_tar = rp_path + '/' + str(rp_num).zfill(2) + '_dirs.tar'
    rp_meta = rp_path + '.meta'
    found_pkgs = set()
    pac_size = 0

    ### Check for Existing Restore Points
    if os.path.exists(rp_path) or os.path.exists(rp_meta):
        if args.no_confirm == False:
            if int(rp_num) != 0:
                prWarning('Restore Point #' + str(rp_num).zfill(2) + ' Already Exists!')
                if YN_Frame('Do You Want to Overwrite It?') == False:
                    return prError('Aborting RP Creation!')
        rm_file(rp_meta, sudo=True)
        rm_dir(rp_path, sudo=True)

    if rp_full == True:
        ### Set Vars For Full RP
        dir_size = 0
        rp_files = set()
        pac_cache = rp_path + '/pac_cache'
        ###################################
        ### Find Pkgs for Restore Point ###
        ###################################
        print('Building Full Restore Point...')
        prWorking('Retrieving Current Packages...')
        pkg_search = pacman_Q(replace_spaces=True)

        ### Search File System for Pkgs
        prWorking('Bulk Scanning for ' + str(len(pkg_search)) + ' Packages...')
        found_pkgs = search_paccache(pkg_search, fetch_paccache())
        pac_size = Size_Of_Files(found_pkgs)

        ### Ask About Missing Pkgs
        if len(found_pkgs) != len(pkg_search):
            if args.no_confirm == False:
                if int(rp_num) != 0:
                    pkg_split = trim_pkg_list(found_pkgs)
                    prError('The Following Packages Where NOT Found!')
                    for pkg in set(pkg_search - pkg_split):
                        prWarning(pkg + ' Was NOT Found!')
                    if YN_Frame('Do You Still Want to Continue?') == False:
                        return prError('Aborting RP Creation!')

        ###############################
        ### HardLink Packages to RP ###
        ###############################
        MK_Dir(rp_path, sudo=False)
        MK_Dir(pac_cache, sudo=False)
        for pkg in tqdm.tqdm(found_pkgs, desc='Hardlinking Packages to Pacback RP'):
            os.system('sudo ln ' + pkg + ' ' + pac_cache + '/' + pkg.split('/')[-1])

        ################################
        ### Find Custom Files for RP ###
        ################################
        if len(dir_list) > 0:
            ### Find and Get Size of Custom Files
            for d in dir_list:
                for f in Search_FS(d, 'set'):
                    ### Some Temp Files Will Return A Size Error
                    try: dir_size += os.path.getsize(f)
                    except: pass
                    rp_files.add(f)

            ### Pack Custom Folders Into a Tar
            with tarfile.open(rp_tar, 'w') as tar:
                for f in tqdm.tqdm(rp_files, desc='Adding Dir\'s to Tar'):
                    tar.add(f)

            ### Compress Custom Files If Added Larger Than 1GB
            if dir_size > 1073741824:
                prWorking('Compressing Restore Point Files...')
                ### Check to See if pigz is Installed
                if any(re.findall('pigz', line.lower()) for line in current_pkgs):
                    os.system('pigz ' + rp_tar + ' -f')
                else:
                    GZ_C(rp_tar, rm=True)

    elif rp_full == False:
        print('Building Light Restore Point...')

    ###############################
    ### Generate Meta Data File ###
    ###############################
    import datetime as dt
    current_pkgs = pacman_Q()
    meta_list = ['====== Pacback RP #'+ str(rp_num).zfill(2) +' ======',
                 'Pacback Version: ' + version,
                 'Date Created: ' + dt.datetime.now().strftime("%Y/%m/%d"),
                 'Packages Installed: ' + str(len(current_pkgs)),
                 'Packages in RP: ' + str(len(found_pkgs)),
                 'Size of Packages in RP: ' + str(Convert_Size(pac_size))]
    
    if args.notes:
        meta_list.append('Notes: ' + args.notes)
    
    if len(dir_list) != 0:
        meta_list.append('Dirs File Count: ' + str(len(rp_files)))
        meta_list.append('Dirs Total Size: ' + Convert_Size(dir_size))
        meta_list.append('')
        meta_list.append('========= Dir List =========')
        for d in dir_list:
            meta_list.append(d)

    meta_list.append('')
    meta_list.append('======= Pacman List ========')
    for pkg in current_pkgs:
        meta_list.append(pkg)

    ### Export Final Meta Data File
    Export_List(rp_meta, meta_list)
    prSuccess('Restore Point #' + str(rp_num).zfill(2) + ' Successfully Created!')


#<#><#><#><#><#><#>#<#>#<#
#+# Rollback to RP
#<#><#><#><#><#><#>#<#>#<#

def rollback_to_rp(rp_num):
    ###########################
    ### Stage Rollback Vars ###
    ###########################
    ### Set Base Var
    rp_path = base_dir + '/restore-points/rp' + str(rp_num).zfill(2)
    rp_tar = rp_path + '/' + str(rp_num).zfill(2) + '_dirs.tar'
    rp_meta = rp_path + '.meta'
    current_pkgs = pacman_Q()
    
    ### Set Full RP Status
    if os.path.exists(rp_path):
        full_rp = True
    else:
        full_rp = False

    ### Set Meta Status, Read Meta, Diff Packages, Set Vars
    if os.path.exists(rp_meta):
        meta_exists = True
        meta = Read_List(rp_meta)
        meta_dirs = Read_Between('========= Dir List =========','======= Pacman List ========', meta)[:-1]
        meta_old_pkgs = Read_Between('======= Pacman List ========','<Endless>', meta)
        
        ### Checking for New and Changed Packages
        changed_pkgs = set(set(meta_old_pkgs) - current_pkgs)
        meta_old_pkg_strp = {pkg.split(' ')[0] for pkg in meta_old_pkgs} ### Strip Version
        current_pkg_strp = {pkg.split(' ')[0] for pkg in current_pkgs} ### Strip Version
        added_pkgs = set(current_pkg_strp - meta_old_pkg_strp)
    
    else:
        meta_exists = False
        meta = None
        
    ### Abort If No Files Are Found
    if meta_exists == False and full_rp == False:
        return prError('Restore Point #' + str(rp_num).zfill(2) + ' Was NOT FOUND!')
    
    ### Compare Versions
    fail = check_pacback_version(version, rp_path, meta_exists, meta)
    if fail == True:
        return prError('Aborting Due to Version Issues!')

    ######################
    ### Start Rollback ###
    ######################
    if full_rp == True:
        rp_cache = rp_path + '/pac_cache'
        
        #~#~#~#~#~#~#~#~#~#~#~#~#~
        #~# Full Restore Point #~#
        #~#~#~#~#~#~#~#~#~#~#~#~#~
        if meta_exists == True:
            ### Pass If No Packages Have Changed
            if len(changed_pkgs) == 0:
                prSuccess('No Packages Have Been Upgraded!')
            else:
                found_pkgs = search_paccache(Replace_Spaces(changed_pkgs), Search_FS(rp_cache, typ='set'))
                os.system('sudo pacman -U ' + ' '.join(found_pkgs))

        elif meta_exists == False:
            os.system('sudo pacman --needed -U ' + rp_cache + '/*')
            prError('Restore Point #' + str(rp_num).zfill(2) + ' Meta Data Was NOT FOUND!')
            return prError('Skipping Advanced Features!')

    elif meta_exists == True and full_rp == False:
       
        #~#~#~#~#~#~#~#~#~#~#~#~#~#
        #~# Light Restore Point #~#
        #~#~#~#~#~#~#~#~#~#~#~#~#~#
        prWorking('Bulk Scanning for ' + str(len(meta_old_pkgs)) + ' Packages...')
        found_pkgs = search_paccache(Replace_Spaces(changed_pkgs), fetch_paccache())

        ### Pass If No Packages Have Changed
        if len(changed_pkgs) == 0:
            prSuccess('No Packages Have Been Upgraded!')

        ### Pass Comparison if All Packages Found
        elif len(found_pkgs) == len(changed_pkgs):
            prSuccess('All Packages Found In Your Local File System!')
            os.system('sudo pacman -U ' + ' '.join(found_pkgs))

        ### Branch if Packages are Missing
        elif len(found_pkgs) < len(changed_pkgs):
            prWarning('Packages Are Missing! Extenting Package Search...')
            found_pkgs = search_paccache(Replace_Spaces(changed_pkgs), fetch_paccache(base_dir + '/restore-points'))
            if len(found_pkgs) == len(changed_pkgs):
                prSuccess('All Packages Found In Your Local File System!')
                os.system('sudo pacman -U ' + ' '.join(found_pkgs))
            else:
                missing_pkg = set(Replace_Spaces(changed_pkgs) - trim_pkg_list(found_pkgs))

                ### Show Missing Pkgs
                prWarning('Couldn\'t Find The Following Package Versions:')
                for pkg in missing_pkg:
                    prError(pkg)
                if YN_Frame('Do You Want To Continue Anyway?') == True:
                    os.system('sudo pacman -U ' + ' '.join(found_pkgs))
                else:
                    return prError('Aborting Rollback!')

    ### Uninstall New Packages? Executes When Meta is True and When Packages Have Been Added
    if len(added_pkgs) > 0:
        prWarning('The Following Packages Are Installed But Are NOT Present in Restore Point #' + str(rp_num).zfill(2) + ':')
        for pkg in added_pkgs:
            prAdded(pkg)
        if YN_Frame('Do You Want to Remove These Packages From Your System?') == True:
            os.system('sudo pacman -R ' + ' '.join(added_pkgs))

    ### Diff Restore Point Files
    if not len(meta_dirs) > 0:
        return prSuccess('Rollback to Restore Point #' + str(rp_num).zfill(2) + ' Complete!')
    else:
        diff_rp_files(rp_tar, meta_dirs, current_pkgs)


#<#><#><#><#><#><#>#<#>#<#
#+# Rollback to Date
#<#><#><#><#><#><#>#<#>#<#

def rollback_to_date(date):
    ### Validate Date Fromat and Build New URL
    if not re.findall(r'([12]\d{3}/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01]))', date):
        return prError('Invalid Date! Date Must be YYYY/MM/DD Format.')

    ### Backup Mirrorlist
    if len(Read_List('/etc/pacman.d/mirrorlist')) > 1:
        os.system('sudo cp /etc/pacman.d/mirrorlist /etc/pacman.d/mirrorlist.pacback')
    os.system("echo 'Server=https://archive.archlinux.org/repos/" + date + "/$repo/os/$arch' | sudo tee /etc/pacman.d/mirrorlist >/dev/null")

    ### Run Pacman Update
    os.system('sudo pacman -Syyuu')


#<#><#><#><#><#><#>#<#>#<#
#+# Unlock Mirrorlist
#<#><#><#><#><#><#>#<#>#<#

def unlock_rollback():
    ### Check if mirrorlist is locked
    if len(Read_List('/etc/pacman.d/mirrorlist')) == 1:
        if os.path.exists('/etc/pacman.d/mirrolist.pacback'):
            list_fetch = YN_Frame('Pacback Can\'t Find Your Backup Mirrorlist! Do You Want to Fetch a New US HTTPS Mirrorlist?')
            if list_fetch == True:
                os.system("curl -s 'https://www.archlinux.org/mirrorlist/?country=US&protocol=https&use_mirror_status=on' | sed -e 's/^#Server/Server/' -e '/^#/d' | sudo tee /etc/pacman.d/mirrorlist.pacback >/dev/null")
            else:
                sys.exit('Critical Error! Please Manually Replace Your Mirrorlist!')
        os.system('sudo cp /etc/pacman.d/mirrorlist.pacback /etc/pacman.d/mirrorlist')
    else:
        return prError('Pacback Does NOT Have an Active Date Lock!')

    ### Update?
    update = YN_Frame('Do You Want to Update Your System Now?')
    if update == True:
        os.system('sudo pacman -Syu')
    if update == False:
        return print('Skipping Update!')


#<#><#><#><#><#><#>#<#>#<#
#+# Rollback Packages
#<#><#><#><#><#><#>#<#>#<#

def rollback_packages(pkg_list):
    prWorking('Searching File System for Packages...')
    cache = fetch_paccache(base_dir + '/restore-points')
    for pkg in pkg_list:
        found_pkgs = user_pkg_search(pkg, cache)
        if len(found_pkgs) > 0:
            prSuccess('Pacback Found the Following Package Versions for ' + pkg + ':')
            answer = Multi_Choice_Frame(found_pkgs)
            if answer == False:
                break
            for x in cache:
                if re.findall(re.escape(answer), x):
                    path = x
            os.system('sudo pacman -U ' + path)
        else:
            prError('No Packages Found Under the Name: ' + pkg)


#<#><#><#><#><#><#>#<#>#<#
#+# CLI Args
#<#><#><#><#><#><#>#<#>#<#

parser = argparse.ArgumentParser(description="A reliable rollback utility for marking and restoring custom save points in Arch Linux.")
#### Pacback -Syu
parser.add_argument("-Syu", "--upgrade", action='store_true', help="Create a light restore point and run a full system upgrade. Use snapback to restore this version state.")
parser.add_argument("-sb", "--snapback", action='store_true', help="Rollback packages to the version state stored before that last pacback upgrade.")
parser.add_argument("--hook", action='store_true', help="Used Exclusivly by the Pacback Hook.")
#### Base RP Functions
parser.add_argument("-rb", "--rollback", metavar=('RP# or YYYY/MM/DD'), help="Rollback to a previously generated restore point or to an archive date.")
parser.add_argument("-pkg", "--rollback_pkgs", nargs='*', default=[], metavar=('PACKAGE_NAME'), help="Rollback a list of packages looking for old versions on the system.")
parser.add_argument("-c", "--create_rp", metavar=('RP#'), help="Generate a pacback restore point. Takes a restore point # as an argument.")
parser.add_argument("-f", "--full_rp", action='store_true', help="Generate a pacback full restore point.")
parser.add_argument("-d", "--add_dir", nargs='*', default=[], metavar=('/PATH'), help="Add any custom directories to your restore point during a `--create_rp AND --full_rp`.")
parser.add_argument("-u", "--unlock_rollback", action='store_true', help="Release any date rollback locks on /etc/pacman.d/mirrorlist. No argument is needed.")
#### Utils
parser.add_argument("-ih", "--install_hook", action='store_true', help="Install a Pacman hook that creates a snapback restore point during each Pacman Upgrade.")
parser.add_argument("-rh", "--remove_hook", action='store_true', help="Remove the Pacman hook that creates a snapback restore point during each Pacman Upgrade.")
parser.add_argument("-i", "--info", metavar=('RP#'), help="Print information about a retore point.")
parser.add_argument("-nc", "--no_confirm", action='store_true', help="Skip asking user questions during RP creation. Will answer yes to all.")
parser.add_argument("-v", "--version", action='store_true', help="Display Pacback Version.")
parser.add_argument("-rm", "--clean", metavar=('# Versions to Keep'), help="Clean Old and Orphaned Pacakages. Provide the number of package you want keep.")
parser.add_argument("-n", "--notes", metavar=('SOME NOTES HERE'), help="Add Custom Notes to Your Metadata File.")
args = parser.parse_args()


#<#><#><#><#><#><#>#<#>#<#
#+# Args Flow Control
#<#><#><#><#><#><#>#<#>#<#
base_dir = os.path.dirname(os.path.realpath(__file__))[:-5]

if args.version:
    print('Pacback Version: ' + version)

if args.info:
    if re.findall(r'^([0-9]|0[1-9]|[1-9][0-9])$', args.info):
        rp = base_dir + '/restore-points/rp' + str(args.info).zfill(2)
        if os.path.exists(rp + '.meta'):
            meta = Read_List(rp + '.meta')
            meta = Read_Between('Pacback RP', 'Pacman List', meta, re_flag=True)
            print('============================')
            for s in meta[:-1]:
                print(s)
            print('============================')

        elif os.path.exists(rp):
            prError('Meta is Missing For This Restore Point!')

        else:
            prError('No Restore Point #' + str(args.info).zfill(2) + ' Was NOT Found!')
    else:
        prError('Info Args Must Be in INT Format!')

if args.clean:
    clean_cache(args.clean, base_dir)

elif args.install_hook:
    pacback_hook(install=True)

elif args.remove_hook:
    pacback_hook(install=False)

elif len(args.rollback_pkgs) > 0:
    rollback_packages(args.rollback_pkgs)

elif args.hook:
    args.no_confirm = True
    create_restore_point('00', args.full_rp, args.add_dir)

elif args.upgrade:
    create_restore_point('00', args.full_rp, args.add_dir)
    os.system('sudo pacman -Syu')

elif args.snapback:
    if os.path.exists(base_dir + '/restore-points/rp00.meta'):
        rollback_to_rp('00')
    else:
        prError('No Snapback Found!')

elif args.rollback:
    if re.findall(r'^([1-9]|0[1-9]|[1-9][0-9])$', args.rollback):
        rollback_to_rp(args.rollback)
    elif re.findall(r'^(?:[0-9]{2})?[0-9]{2}/[0-3]?[0-9]/(?:[0-9]{2})?[0-9]{2}$', args.rollback):
        rollback_to_date(args.rollback)
    else:
        prError('No Usable Argument! Rollback Arg Must be a Restore Point # or a Date.')

elif args.create_rp:
    if re.findall(r'^([1-9]|0[1-9]|[1-9][0-9])$', args.create_rp):
        create_restore_point(args.create_rp, args.full_rp, args.add_dir)
    else:
        prError('Create RP Args Must Be INT or Date! Refer to Documentation for Help.')

elif args.unlock_rollback:
    unlock_rollback()

elif not args.info or not args.version:
    pass

else:
    prError('No Usable Argument Given!')
