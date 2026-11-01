# Copyright 2015 Agile Business Group <http://www.agilebg.com>
# Copyright 2015 Alessio Gerace <alesiso.gerace@agilebg.com>
# Copyright 2016 Grupo ESOC Ingenieria de Servicios, S.L.U. - Jairo Llopis
# Copyright 2016 LasLabs Inc.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import PropertyMock, patch

import paramiko

from odoo import tools
from odoo.exceptions import UserError
from odoo.tests import common

_logger = logging.getLogger(__name__)


model = "odoo.addons.auto_backup.models.db_backup"
class_name = f"{model}.DbBackup"


class TestConnectionException(paramiko.SSHException):
    def __init__(self):
        super().__init__("test")


class TestDbBackup(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.Model = self.env["db.backup"]

    @contextmanager
    def mock_assets(self):
        """It provides mocked core assets"""
        self.path_join_val = "/this/is/a/path"
        with patch(f"{model}.db") as db:
            with patch(f"{model}.os") as os:
                with patch(f"{model}.shutil") as shutil:
                    os.path.join.return_value = self.path_join_val
                    yield {
                        "db": db,
                        "os": os,
                        "shutil": shutil,
                    }

    @contextmanager
    def patch_filtered_sftp(self, record):
        """It patches filtered record and provides a mock"""
        with patch(f"{class_name}.filtered") as filtered:
            filtered.side_effect = [], [record]
            with patch(f"{class_name}.backup_log"):
                with patch(f"{class_name}.sftp_connection"):
                    yield filtered

    def new_record(self, method="sftp"):
        vals = {"name": "Têst backup", "method": method, "days_to_keep": 1}
        if method == "sftp":
            vals.update(
                {
                    "sftp_host": "test_host",
                    "sftp_port": "222",
                    "sftp_user": "tuser",
                    "sftp_password": "password",
                    "folder": "/folder/",
                }
            )
        self.vals = vals
        return self.Model.create(vals)

    def test_compute_name_sftp(self):
        """It should create proper SFTP URI"""
        rec_id = self.new_record()
        expected_uri = (
            f"sftp://{self.vals['sftp_user']}@{self.vals['sftp_host']}:"
            f"{self.vals['sftp_port']}{self.vals['folder']}"
        )
        self.assertEqual(expected_uri, rec_id.name)

    def test_check_folder(self):
        """It should not allow recursive backups"""
        rec_id = self.new_record("local")
        with self.assertRaises(UserError):
            rec_id.write(
                {
                    "folder": (
                        f"{tools.config.filestore(self.env.cr.dbname)}" "/another/path"
                    ),
                }
            )

    @patch(f"{model}._")
    def test_action_sftp_test_connection_success(self, _):
        """It should raise connection succeeded warning"""
        with patch(f"{class_name}.sftp_connection", new_callable=PropertyMock):
            rec_id = self.new_record()
            with self.assertRaises(UserError):
                rec_id.action_sftp_test_connection()
        _.assert_called_once_with("Connection Test Succeeded!")

    @patch(f"{model}._")
    def _test_action_sftp_test_connection_fail(self, _):
        """It should raise connection fail warning"""
        with patch(f"{class_name}.sftp_connection", new_callable=PropertyMock) as conn:
            rec_id = self.new_record()
            conn().side_effect = TestConnectionException
            with self.assertRaises(UserError):
                rec_id.action_sftp_test_connection()
            _.assert_called_once_with("Connection Test Failed!")

    def test_action_backup_local(self):
        """It should backup local database"""
        rec_id = self.new_record("local")
        filename = rec_id.filename(datetime.now())
        rec_id.action_backup()
        generated_backup = [f for f in os.listdir(rec_id.folder) if f >= filename]
        self.assertEqual(1, len(generated_backup))

    def test_action_backup_local_cleanup(self):
        """Backup local database and cleanup old databases"""
        rec_id = self.new_record("local")
        old_date = datetime.now() - timedelta(days=3)
        filename = rec_id.filename(old_date)
        with patch(f"{model}.datetime") as mock_date:
            mock_date.now.return_value = old_date
            rec_id.action_backup()
        generated_backup = [f for f in os.listdir(rec_id.folder) if f >= filename]
        self.assertEqual(2, len(generated_backup))

        filename = rec_id.filename(datetime.now())
        rec_id.action_backup()
        generated_backup = [f for f in os.listdir(rec_id.folder) if f >= filename]
        self.assertEqual(1, len(generated_backup))

    def _test_action_backup_sftp_mkdirs(self):
        """It should create remote dirs"""
        rec_id = self.new_record()
        with self.mock_assets():
            with self.patch_filtered_sftp(rec_id):
                with patch(f"{class_name}.cleanup", new_callable=PropertyMock):
                    with patch(f"{class_name}._sftp_makedirs") as makedirs:
                        conn = rec_id.sftp_connection().__enter__()
                        rec_id.action_backup()
                        makedirs.assert_called_once_with(conn, rec_id.folder)

    def _test_action_backup_sftp_mkdirs_conn_exception(self):
        """It should guard from an SSH error while creating remote dirs"""
        rec_id = self.new_record()
        with self.mock_assets():
            with self.patch_filtered_sftp(rec_id):
                with patch(f"{class_name}.cleanup", new_callable=PropertyMock):
                    with patch(f"{class_name}._sftp_makedirs") as makedirs:
                        makedirs.side_effect = TestConnectionException
                        rec_id.action_backup()
                    # No error was raised, test pass
                    self.assertTrue(True)

    def test_action_backup_sftp_remote_open(self):
        """It should open remote file w/ proper args"""
        rec_id = self.new_record()
        with self.mock_assets() as assets:
            with self.patch_filtered_sftp(rec_id):
                with patch(f"{class_name}.cleanup", new_callable=PropertyMock):
                    conn = rec_id.sftp_connection().__enter__()
                    rec_id.action_backup()
                    conn.open.assert_called_once_with(assets["os"].path.join(), "wb")

    def test_action_backup_all_search(self):
        """It should search all records"""
        rec_id = self.new_record()
        with patch(f"{class_name}.search", new_callable=PropertyMock):
            rec_id.action_backup_all()
            rec_id.search.assert_called_once_with([])

    def test_action_backup_all_return(self):
        """It should return result of backup operation"""
        rec_id = self.new_record()
        with patch(f"{class_name}.search", new_callable=PropertyMock):
            res = rec_id.action_backup_all()
            self.assertEqual(rec_id.search().action_backup(), res)

    @patch(f"{model}.paramiko.SSHClient")
    def test_sftp_connection_init_passwd(self, ssh_client):
        """It should connect with the password, without searching keys"""
        rec_id = self.new_record()
        with rec_id.sftp_connection():
            pass
        ssh_client.return_value.connect.assert_called_once_with(
            hostname=rec_id.sftp_host,
            port=rec_id.sftp_port,
            username=rec_id.sftp_user,
            password=rec_id.sftp_password,
            allow_agent=False,
            look_for_keys=False,
        )

    @patch(f"{model}.paramiko.SSHClient")
    def test_sftp_connection_init_key(self, ssh_client):
        """It should connect with the key file and its passphrase"""
        rec_id = self.new_record()
        rec_id.write({"sftp_private_key": "pkey", "sftp_password": "pkeypass"})
        with rec_id.sftp_connection():
            pass
        ssh_client.return_value.connect.assert_called_once_with(
            hostname=rec_id.sftp_host,
            port=rec_id.sftp_port,
            username=rec_id.sftp_user,
            key_filename=rec_id.sftp_private_key,
            passphrase=rec_id.sftp_password,
            allow_agent=False,
            look_for_keys=False,
        )

    @patch(f"{model}.paramiko.SSHClient")
    def test_sftp_connection_return(self, ssh_client):
        """It should yield the SFTP client and close the session after"""
        rec_id = self.new_record()
        client = ssh_client.return_value
        with rec_id.sftp_connection() as remote:
            self.assertEqual(client.open_sftp().__enter__(), remote)
            client.close.assert_not_called()
        client.close.assert_called_once_with()

    @patch(f"{model}.paramiko.SSHClient")
    def test_sftp_connection_closes_on_error(self, ssh_client):
        """It should close the session when the connection fails"""
        rec_id = self.new_record()
        client = ssh_client.return_value
        client.connect.side_effect = paramiko.AuthenticationException
        with (
            self.assertRaises(paramiko.AuthenticationException),
            rec_id.sftp_connection(),
        ):
            pass
        client.close.assert_called_once_with()

    @patch.object(paramiko.SSHClient, "open_sftp")
    @patch.object(paramiko.SSHClient, "connect", autospec=True)
    def test_sftp_connection_host_key(self, connect, open_sftp):
        """It should require the configured host key, port included"""
        rec_id = self.new_record()
        key = paramiko.RSAKey.generate(2048)
        rec_id.write(
            {
                "sftp_port": 2222,
                "sftp_public_host_key": key.get_base64(),
                "sftp_public_encryption": "rsa-key",
            }
        )
        with rec_id.sftp_connection():
            pass
        client = connect.call_args.args[0]
        host_key = client.get_host_keys().lookup(f"[{rec_id.sftp_host}]:2222")
        self.assertEqual(key, host_key["ssh-rsa"])
        self.assertIsInstance(client._policy, paramiko.RejectPolicy)

    def test_sftp_makedirs(self):
        """It should create the missing parents and keep the existing ones"""
        existing = {"/backups"}
        created = []

        class FakeSftp:
            def stat(self, path):
                if path not in existing and path not in created:
                    raise FileNotFoundError(2, "No such file")

            def mkdir(self, path):
                created.append(path)

        self.Model._sftp_makedirs(FakeSftp(), "/backups/db/daily")
        self.assertEqual(["/backups/db", "/backups/db/daily"], created)

    def test_filename_default(self):
        """It should not error and should return a .dump.zip file str"""
        now = datetime.now()
        res = self.Model.filename(now)
        self.assertTrue(res.endswith(".dump.zip"))

    def test_filename_zip(self):
        """It should return a dump.zip filenam"""
        now = datetime.now()
        res = self.Model.filename(now, ext="zip")
        self.assertTrue(res.endswith(".dump.zip"))

    def test_filename_dump(self):
        """It should return a dump filenam"""
        now = datetime.now()
        res = self.Model.filename(now, ext="dump")
        self.assertTrue(res.endswith(".dump"))
