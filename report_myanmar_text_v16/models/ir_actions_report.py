from urllib.parse import urlparse
from odoo import api, fields, models, tools, SUPERUSER_ID, _
from odoo.exceptions import UserError, AccessError
from odoo.tools.misc import find_in_path, ustr
from odoo.http import request
import os
import tempfile
import subprocess
from contextlib import closing

def _get_wkhtmltopdf_bin():
    return find_in_path('wkhtmltopdf')


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _run_wkhtmltopdf(
            self,
            bodies,
            report_ref=False,
            header=None,
            footer=None,
            landscape=False,
            specific_paperformat_args=None,
            set_viewport_size=False):
        '''Execute wkhtmltopdf as a subprocess in order to convert html given in input into a pdf
        document.

        :param list[str] bodies: The html bodies of the report, one per page.
        :param report_ref: report reference that is needed to get report paperformat.
        :param str header: The html header of the report containing all headers.
        :param str footer: The html footer of the report containing all footers.
        :param landscape: Force the pdf to be rendered under a landscape format.
        :param specific_paperformat_args: dict of prioritized paperformat arguments.
        :param set_viewport_size: Enable a viewport sized '1024x1280' or '1280x1024' depending of landscape arg.
        :return: Content of the pdf as bytes
        :rtype: bytes
        '''
        paperformat_id = self._get_report(report_ref).get_paperformat() if report_ref else self.get_paperformat()

        # Build the base command args for wkhtmltopdf bin
        command_args = self._build_wkhtmltopdf_args(
            paperformat_id,
            landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size)

        files_command_args = []
        temporary_files = []

        # Passing the cookie to wkhtmltopdf in order to resolve internal links.
        if request and request.db:
            base_url = self._get_report_url()
            domain = urlparse(base_url).hostname
            cookie = f'session_id={request.session.sid}; HttpOnly; domain={domain}; path=/;'
            cookie_jar_file_fd, cookie_jar_file_path = tempfile.mkstemp(suffix='.txt', prefix='report.cookie_jar.tmp.')
            temporary_files.append(cookie_jar_file_path)
            with closing(os.fdopen(cookie_jar_file_fd, 'wb')) as cookie_jar_file:
                cookie_jar_file.write(cookie.encode())
            command_args.extend(['--cookie-jar', cookie_jar_file_path])

        if header:
            head_file_fd, head_file_path = tempfile.mkstemp(suffix='.html', prefix='report.header.tmp.')
            with closing(os.fdopen(head_file_fd, 'wb')) as head_file:
                # Reshape the Myanmar text for PDF report
                header = self._myanmar_text_reshaper(header)
                head_file.write(header.encode())
            temporary_files.append(head_file_path)
            files_command_args.extend(['--header-html', head_file_path])
        if footer:
            foot_file_fd, foot_file_path = tempfile.mkstemp(suffix='.html', prefix='report.footer.tmp.')
            with closing(os.fdopen(foot_file_fd, 'wb')) as foot_file:
                # Reshape the Myanmar text for PDF report
                footer = self._myanmar_text_reshaper(footer)
                foot_file.write(footer.encode())
            temporary_files.append(foot_file_path)
            files_command_args.extend(['--footer-html', foot_file_path])

        paths = []
        for i, body in enumerate(bodies):
            prefix = '%s%d.' % ('report.body.tmp.', i)
            body_file_fd, body_file_path = tempfile.mkstemp(suffix='.html', prefix=prefix)
            with closing(os.fdopen(body_file_fd, 'wb')) as body_file:
                # Reshape the Myanmar text for PDF report
                body = self._myanmar_text_reshaper(body)
                body_file.write(body.encode())
            paths.append(body_file_path)
            temporary_files.append(body_file_path)

        pdf_report_fd, pdf_report_path = tempfile.mkstemp(suffix='.pdf', prefix='report.tmp.')
        os.close(pdf_report_fd)
        temporary_files.append(pdf_report_path)

        try:
            wkhtmltopdf = [_get_wkhtmltopdf_bin()] + command_args + files_command_args + paths + [pdf_report_path]
            process = subprocess.Popen(wkhtmltopdf, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = process.communicate()
            err = ustr(err)

            if process.returncode not in [0, 1]:
                if process.returncode == -11:
                    message = _(
                        'Wkhtmltopdf failed (error code: %s). Memory limit too low or maximum file number of subprocess reached. Message : %s')
                else:
                    message = _('Wkhtmltopdf failed (error code: %s). Message: %s')
                _logger.warning(message, process.returncode, err[-1000:])
                raise UserError(message % (str(process.returncode), err[-1000:]))
            else:
                if err:
                    _logger.warning('wkhtmltopdf: %s' % err)
        except:
            raise

        with open(pdf_report_path, 'rb') as pdf_document:
            pdf_content = pdf_document.read()

        # Manual cleanup of the temporary files
        for temporary_file in temporary_files:
            try:
                os.unlink(temporary_file)
            except (OSError, IOError):
                _logger.error('Error when trying to remove file %s' % temporary_file)

        return pdf_content

    # Reshape the Myanmar text for PDF reports
    def _myanmar_text_reshaper(self, html):
        html_list = list(html)

        # Step - 1: Reorder the characters
        ###########
        # Reorder the 'ThaWaiHtoo' character
        for i, v in enumerate(html_list):
            if v == '\u1031':
                if html_list[i - 1] in ['\u103B', '\u103C', '\u103D', '\u103E']:
                    html_list[i - 1], html_list[i] = html_list[i], html_list[i - 1]
                    if html_list[i - 2] in ['\u103B', '\u103C', '\u103D', '\u103E']:
                        html_list[i - 2], html_list[i - 1] = html_list[i - 1], html_list[i - 2]
                        if html_list[i - 3] in ['\u103B', '\u103C', '\u103D', '\u103E']:
                            html_list[i - 3], html_list[i - 2] = html_list[i - 2], html_list[i - 3]

        # Reorder the 'YaYit' character
        for i, v in enumerate(html_list):
            if v == '\u103C':
                if html_list[i - 1] == '\u1031':
                    html_list[i - 2], html_list[i - 1], html_list[i] = '\u001D\u1031', html_list[i], html_list[i - 2]
                else:
                    html_list[i - 1], html_list[i] = html_list[i], html_list[i - 1]

        # Step 2: Character sustitutions
        #########
        # 'YaYit' character substitutions
        for i, v in enumerate(html_list):
            if v == '\u103C':
                if html_list[i + 1] in ['\u1000', '\u1003', '\u100F', '\u1006', '\u1010', '\u1011',
                                        '\u1018', '\u101A', '\u101C', '\u101E', '\u101F', '\u1021']:
                    html_list[i] = '\uE1B2'

        # One-to-One character substitutions
        for i, v in enumerate(html_list):
            if v == '\u1014':
                if html_list[i + 1] in ['\u102F', '\u1030', '\u103D', '\u103E']:
                    html_list[i] = '\uE107'
                if html_list[i + 2] in ['\u102F', '\u1030']:
                    html_list[i] = '\uE107'
                if html_list[i + 1] == '\u1031':
                    if html_list[i + 2] in ['\u102F', '\u1030', '\u103D', '\u103E']:
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\u001D\u1031', '\uE107', html_list[i + 2]
            if v == '\u101B':
                if html_list[i + 1] in ['\u102F', '\u1030']: html_list[i] = '\uE108'
                if html_list[i + 2] in ['\u102F', '\u1030']: html_list[i] = '\uE108'
                if html_list[i + 3] in ['\u102F', '\u1030']: html_list[i] = '\uE108'
            if v == '\u102F':
                if html_list[i - 1] == '\u103B' or html_list[i - 2] == '\u103B':
                    html_list[i] = '\uE2F1'
                if html_list[i - 2] in ['\u103C', '\uE1B2'] or html_list[i - 3] in ['\u103C', '\uE1B2']:
                    html_list[i] = '\uE2F1'
            if v == '\u1030':
                if html_list[i - 1] == '\u103B' or html_list[i - 2] == '\u103B':
                    html_list[i] = '\uE2F2'
                if html_list[i - 2] in ['\u103C', '\uE1B2'] or html_list[i - 3] in ['\u103C', '\uE1B2']:
                    html_list[i] = '\uE2F2'
            if v == '\u1037':
                if html_list[i - 1] in ['\u102F', '\u1030']:
                    html_list[i] = '\uE037'
                if html_list[i - 1] == '\u1014' or html_list[i - 2] == '\u1014':
                    html_list[i] = '\uE037'
                if html_list[i - 1] == '\u101B' or html_list[i - 2] == '\u101B' or html_list[i - 3] == '\u101B':
                    html_list[i] = '\uE137'
                if html_list[i - 1] in ['\uE2F1', '\uE2F2']:
                    html_list[i] = '\uE137'
                if html_list[i - 1] == '\u103D' or html_list[i - 2] == '\u103D':
                    html_list[i] = '\uE137'
                if html_list[i - 1] == '\u103B' or html_list[i - 2] == '\u103B':
                    html_list[i] = '\uE137'
            if v == '\u103E':
                if html_list[i - 2] in ['\u103C', '\uE1B2']:
                    html_list[i] = '\uE1F3'

        # Two-to-One character substitutions
        for i, v in enumerate(html_list):
            if v == '\u102D':
                if html_list[i + 1] == '\u1036':
                    html_list[i], html_list[i + 1] = '\uE2D1', ''
                if html_list[i + 1] == '\u1032':
                    html_list[i], html_list[i + 1] = '\uE12D', ''
            if v == '\u102B':
                if html_list[i + 1] == '\u103A':
                    html_list[i], html_list[i + 1] = '\uE02D', ''
                if html_list[i + 1] == '\u1032':
                    html_list[i], html_list[i + 1] = '\uE52C', ''
                if html_list[i + 1] == '\u1036':
                    html_list[i], html_list[i + 1] = '\uE52B', ''
            if v == '\u103B':
                if html_list[i + 1] == '\u103D':
                    html_list[i], html_list[i + 1] = '\uE1A4', ''
                    if html_list[i + 2] == '\u103E':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE1D1', '\u103B', ''
                if html_list[i + 1] == '\u103E':
                    html_list[i], html_list[i + 1] = '\uE1A3', ''
            if v == '\u103D':
                if html_list[i + 1] == '\u103E':
                    html_list[i], html_list[i + 1] = '\uE1D1', ''
            if v == '\u102F':
                if html_list[i - 1] == '\u103E':
                    html_list[i - 1], html_list[i] = '\uE1F2', ''
                if html_list[i - 2] == '\u103E':
                    html_list[i - 2], html_list[i] = '\uE1F2', ''
            if v == '\u1030':
                if html_list[i - 1] == '\u103E':
                    html_list[i - 1], html_list[i] = '\uE430', ''
                if html_list[i - 2] == '\u103E':
                    html_list[i - 2], html_list[i] = '\uE430', ''

        # Virama character substitutions
        for i, v in enumerate(html_list):
            if v == '\u1039':
                if html_list[i - 1] == '\u103A' and html_list[i - 2] == '\u1004':
                    html_list[i - 2], html_list[i - 1], html_list[i] = '', '', '\uE390'
                    if html_list[i + 1] == '\u103C':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE1B6', html_list[i + 2], html_list[i]
                    elif html_list[i + 1] == '\uE1B2':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE1B7', html_list[i + 2], html_list[i]
                    else:
                        html_list[i], html_list[i + 1] = html_list[i + 1], html_list[i]
                else:
                    if html_list[i + 1] == '\u1000': html_list[i], html_list[i + 1] = '\uE000', ''
                    if html_list[i + 1] == '\u1001': html_list[i], html_list[i + 1] = '\uE001', ''
                    if html_list[i + 1] == '\u1002': html_list[i], html_list[i + 1] = '\uE002', ''
                    if html_list[i + 1] == '\u1003': html_list[i], html_list[i + 1] = '\uE003', ''

                    if html_list[i + 1] == '\u1005': html_list[i], html_list[i + 1] = '\uE005', ''
                    if html_list[i + 1] == '\u1006': html_list[i], html_list[i + 1] = '\uE006', ''
                    if html_list[i + 1] == '\u1007': html_list[i], html_list[i + 1] = '\uE007', ''
                    if html_list[i + 1] == '\u1008': html_list[i], html_list[i + 1] = '\uE008', ''

                    if html_list[i + 1] == '\u100A': html_list[i], html_list[i + 1] = '\uE00A', ''
                    if html_list[i + 1] == '\u100B': html_list[i], html_list[i + 1] = '\uE00B', ''
                    if html_list[i + 1] == '\u100C': html_list[i], html_list[i + 1] = '\uE00C', ''
                    if html_list[i - 1] == '\u100F' and html_list[i + 1] == '\u100D':
                        html_list[i - 1], html_list[i], html_list[i + 1] = '\uE105', '', ''
                    elif html_list[i + 1] == '\u100D':
                        html_list[i], html_list[i + 1] = '\uE00D', ''
                    if html_list[i + 1] == '\u100E': html_list[i], html_list[i + 1] = '\uE00E', ''
                    if html_list[i + 1] == '\u100F': html_list[i], html_list[i + 1] = '\uE00F', ''

                    if html_list[i + 1] == '\u1010': html_list[i], html_list[i + 1] = '\uE010', ''
                    if html_list[i + 1] == '\u1011': html_list[i], html_list[i + 1] = '\uE011', ''
                    if html_list[i + 1] == '\u1012': html_list[i], html_list[i + 1] = '\uE012', ''
                    if html_list[i + 1] == '\u1013': html_list[i], html_list[i + 1] = '\uE013', ''
                    if html_list[i + 1] == '\u1014': html_list[i], html_list[i + 1] = '\uE014', ''
                    if html_list[i + 1] == '\u1015': html_list[i], html_list[i + 1] = '\uE015', ''
                    if html_list[i + 1] == '\u1016': html_list[i], html_list[i + 1] = '\uE016', ''
                    if html_list[i + 1] == '\u1017': html_list[i], html_list[i + 1] = '\uE017', ''
                    if html_list[i + 1] == '\u1018': html_list[i], html_list[i + 1] = '\uE018', ''
                    if html_list[i + 1] == '\u1019': html_list[i], html_list[i + 1] = '\uE019', ''

                    if html_list[i + 1] == '\u101C': html_list[i], html_list[i + 1] = '\uE01C', ''
                    if html_list[i + 1] == '\u101E': html_list[i], html_list[i + 1] = '\uE01E', ''
                    if html_list[i + 1] == '\u101F': html_list[i], html_list[i + 1] = '\uE553', ''
                    if html_list[i + 1] == '\u1021': html_list[i], html_list[i + 1] = '\uE021', ''

                    if html_list[i + 2] == '\u102F': html_list[i + 2] = '\uE2F1'
                    if html_list[i + 2] == '\u1030': html_list[i + 2] = '\uE2F2'
                    if html_list[i - 1] == '\u1014': html_list[i - 1] = '\uE107'

        # 'KinSi' variant substitutions
        for i, v in enumerate(html_list):
            if v == '\uE390':
                if html_list[i + 1] == '\u103B':
                    if html_list[i + 2] == '\u102E':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE392', html_list[i + 1], ''
                    if html_list[i + 2] == '\u102D':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE391', html_list[i + 1], ''
                    if html_list[i + 2] == '\u1032':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE396', html_list[i + 1], ''
                    if html_list[i + 2] == '\u1036':
                        html_list[i], html_list[i + 1], html_list[i + 2] = '\uE393', html_list[i + 1], ''
                else:
                    if html_list[i + 1] == '\u102E':
                        html_list[i], html_list[i + 1] = '\uE392', ''
                    if html_list[i + 1] == '\u102D':
                        html_list[i], html_list[i + 1] = '\uE391', ''
                    if html_list[i + 1] == '\u1032':
                        html_list[i], html_list[i + 1] = '\uE396', ''
                    if html_list[i + 1] == '\u1036':
                        html_list[i], html_list[i + 1] = '\uE393', ''

        # 'YaYit' variant substitutions
        for i, v in enumerate(html_list):
            if v == '\u103C':
                if html_list[i + 2] in ['\u102D', '\u102E', '\u1032']:
                    html_list[i] = '\uE1B6'
                if html_list[i + 2] == '\u103D':
                    html_list[i] = '\uE1BB'
                    if html_list[i + 3] in ['\u102D', '\u102E', '\u1032']:
                        html_list[i] = '\uE1B6'
            if v == '\uE1B2':
                if html_list[i + 2] in ['\u102D', '\u102E', '\u1032']:
                    html_list[i] = '\uE1B7'
                if html_list[i + 2] == '\u103D':
                    html_list[i] = '\uE1BC'
                    if html_list[i + 3] in ['\u102D', '\u102E', '\u1032']:
                        html_list[i] = '\uE1B7'

        reshape_html = ''.join(map(str, html_list))
        return reshape_html
