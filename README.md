# Interface CAT para o Yaesu FTX-1

Aplicativo desktop em Python/Tkinter para consultar e alterar configurações do
Yaesu FTX-1 pela porta serial CAT. A interface inclui a tabela de menus CAT,
leitura e gravação dos itens suportados, backup/restauração em JSON e uma aba de
controles rápidos para CH STEP, RF POWER, D-LEVEL, NB, DNR e a função do knob
FUNC.

## Requisitos

- Python 3.8 ou superior, com Tkinter
- `pyserial`
- Cabo USB conectado à porta **Enhanced COM Port (CAT-1)** do rádio

## Executar no Windows

Abra um terminal nesta pasta e execute:

```powershell
py -m pip install -r requirements.txt
py ftx1_cat_menu.py
```

No programa, escolha a porta CAT-1 e a taxa configurada no rádio (38400 bps é a
taxa padrão), depois clique em **Conectar**. O aplicativo identifica o rádio
antes de liberar as operações CAT.

## Arquivos

- `ftx1_cat_menu.py`: interface gráfica e operações do aplicativo.
- `ftx1_menu.py`: tabela de menus/comandos EX e transporte serial CAT.
- `requirements.txt`: dependências Python.

Manuais PDF, caches Python, ambientes virtuais e backups de configuração ficam
fora do Git para evitar incluir arquivos locais no repositório por acidente.
