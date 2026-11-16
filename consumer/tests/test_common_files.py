"""Utilitários de arquivos e regra de auditoria em common.py."""
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

import common


# --- move_file ---------------------------------------------------------------

def test_move_o_arquivo_e_cria_a_pasta_de_destino(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')
    destination = tmp_path / 'drive' / 'empresa' / 'base' / 'origem.pdf'

    assert common.move_file(source, destination) is True
    assert destination.read_bytes() == b'novo'
    assert not source.exists()


def test_mantem_a_origem_quando_delete_on_move_e_falso(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')
    destination = tmp_path / 'destino.pdf'

    common.move_file(source, destination, delete_on_move=False)

    assert source.exists()
    assert destination.read_bytes() == b'novo'


def test_arquivo_existente_vai_para_backup_bot(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')
    destination = tmp_path / 'base' / 'relatorio.pdf'
    destination.parent.mkdir()
    destination.write_bytes(b'antigo')

    common.move_file(source, destination)

    assert destination.read_bytes() == b'novo'
    assert (destination.parent / 'backup - bot' / 'relatorio.pdf').read_bytes() == b'antigo'


def test_backup_anterior_e_substituido(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')
    destination = tmp_path / 'base' / 'relatorio.pdf'
    backup = destination.parent / 'backup - bot' / 'relatorio.pdf'
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b'muito antigo')
    destination.write_bytes(b'antigo')

    common.move_file(source, destination)

    assert backup.read_bytes() == b'antigo'


def test_sem_backup_sobrescreve_o_destino(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')
    destination = tmp_path / 'base' / 'relatorio.pdf'
    destination.parent.mkdir()
    destination.write_bytes(b'antigo')

    common.move_file(source, destination, backup_old_file=False)

    assert destination.read_bytes() == b'novo'
    assert not (destination.parent / 'backup - bot').exists()


def test_recusa_caminhos_em_texto(tmp_path):
    source = tmp_path / 'origem.pdf'
    source.write_bytes(b'novo')

    assert common.move_file(str(source), str(tmp_path / 'destino.pdf')) is False
    assert source.exists()


# --- clear_folder ------------------------------------------------------------

def test_clear_folder_apaga_arquivos_e_mantem_pastas(tmp_path):
    folder = tmp_path / 'downloads'
    (folder / 'sub').mkdir(parents=True)
    (folder / 'a.pdf').write_bytes(b'1')
    (folder / 'sub' / 'b.pptx').write_bytes(b'2')

    common.clear_folder(folder)

    assert list(folder.rglob('*.*')) == []
    assert (folder / 'sub').is_dir()


def test_clear_folder_nao_apaga_arquivo_sem_extensao(tmp_path):
    """Documenta o comportamento atual: o padrão '*.*' ignora arquivos sem extensão."""
    folder = tmp_path / 'downloads'
    folder.mkdir()
    (folder / 'sem_extensao').write_bytes(b'1')

    common.clear_folder(folder)

    assert (folder / 'sem_extensao').exists()


# --- unzip -------------------------------------------------------------------

def make_zip(path, name, content):
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(name, content)


def test_unzip_numera_arquivos_com_o_mesmo_nome(tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'base.csv').write_text('original', encoding='utf-8')
    for i in range(2):
        archive = tmp_path / f'lote{i}.zip'
        make_zip(archive, 'base.csv', f'lote {i}')
        common.unzip(archive, out)

    assert (out / 'base.csv').read_text(encoding='utf-8') == 'original'
    assert (out / 'base (1).csv').read_text(encoding='utf-8') == 'lote 0'
    assert (out / 'base (2).csv').read_text(encoding='utf-8') == 'lote 1'


def test_unzip_remove_o_zip_quando_pedido(tmp_path):
    archive = tmp_path / 'lote.zip'
    make_zip(archive, 'base.csv', 'x')

    common.unzip(archive, tmp_path / 'out', remove_on_extract=True)

    assert not archive.exists()
    assert (tmp_path / 'out' / 'base.csv').exists()


# --- need_audith -------------------------------------------------------------

def fixed_month(monkeypatch, month):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, month, 15, 10, 0, 0, tzinfo=tz)

    monkeypatch.setattr(common, 'datetime', FixedDatetime)


@pytest.mark.parametrize('product, audit_date, current_month, expected', [
    ('Controle 6M', '2026-05-10', 11, True),    # semestral: 05 e 11
    ('Controle 6M', '2026-05-10', 10, False),
    ('controle 300', '2026-01-10', 7, True),    # semestral: 01 e 07
    ('Gestão', '2026-02-01', 11, True),         # trimestral: 02, 05, 08, 11
    ('Controle', '2026-02-01', 12, False),
    ('Suri Beta', '2026-03-01', 9, True),
    ('Produto Novo', '2026-03-01', 3, False),   # produto sem regra
])
def test_regra_de_auditoria_pelo_produto_e_pelo_mes(monkeypatch, product, audit_date, current_month, expected):
    fixed_month(monkeypatch, current_month)

    result = common.need_audith(None, 'Empresa', audit_date, product, discord_user_id=None)

    assert result is expected


def test_sem_data_de_auditoria_nao_audita(monkeypatch):
    fixed_month(monkeypatch, 5)

    assert common.need_audith(None, 'Empresa', None, 'Controle 6M', None) is False


def test_usuario_do_discord_pode_dispensar_a_auditoria(monkeypatch):
    fixed_month(monkeypatch, 11)  # pela regra, auditaria

    assert common.need_audith(False, 'Empresa', '2026-05-10', 'Controle 6M', discord_user_id='123') is False


def test_usuario_do_discord_pode_pedir_a_auditoria(monkeypatch):
    fixed_month(monkeypatch, 10)  # pela regra, não auditaria

    assert common.need_audith(True, 'Empresa', '2026-05-10', 'Controle 6M', discord_user_id='123') is True


def test_pedido_do_trello_segue_a_regra(monkeypatch):
    fixed_month(monkeypatch, 10)

    assert common.need_audith(True, 'Empresa', '2026-05-10', 'Controle 6M', discord_user_id=None) is False
