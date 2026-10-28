# Yaesu FTX-1 CAT Menu — by PR2EM

![Status: v0.1 Alpha](https://img.shields.io/badge/status-v0.1--alpha-orange)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blueviolet)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey)

> A Python desktop application for reading and controlling the Yaesu FTX-1 transceiver through its serial CAT interface. It brings together quick operating controls, band selection, and CAT menu parameter management.

> **Version:** 0.1 Alpha. This project is under development. Use care when writing settings to your radio.

## 🚀 Features

- **CAT connection:** automatically detects and selects the Silicon Labs CP2105 `Enhanced COM Port` when available. The connection opens after you click **Connect**.
- **Radio identification:** reads the radio ID and MAIN firmware version after connecting.
- **MAIN tuning:** displays the current frequency and periodically tracks changes made with the radio's physical dial.
- **Direct frequency entry:** accepts abbreviated numeric input and applies separators automatically; for example, `1448` becomes `144.800.000 Hz` and `27555` becomes `27.555.000 Hz`.
- **On-screen dial:** changes frequency with the mouse wheel.
- **Band selection:** buttons request the FTX-1 CAT band selection and use the radio's internal Band Stack rather than sending a fixed frequency. Since the CAT Band Select list has no 11 m entry, the **11m** button directly tunes to 27.555 MHz (DX calling frequency) while keeping the current mode.
- **Mode selection:** buttons select available MAIN operating modes.
- **CH-STEP:** a vertical slider adapts to the current mode and supports dragging, clicking the scale, and mouse wheel adjustment.
- **Quick controls:** sliders adjust RF POWER, D-LEVEL, D-PEAK, NB, and DNR and send changes while you adjust them.
- **FUNC parameters:** select a parameter to adjust locally without changing the assignment of the radio's physical FUNC button.
- **CAT menu:** search and read menu items; supported items can be written individually or in batches.
- **Backup and restore:** saves read settings to JSON and compares a backup with the current state before restoring compatible values.
- **Communication log:** reports operation progress and can show CAT commands sent and received.

## 🛠️ Technologies and resources

### Language

- Python 3.8 or newer.

### Libraries and frameworks

- **Tkinter / ttk:** graphical interface.
- **pyserial 3.5:** serial port discovery and CAT communication.
- **Python standard library:** including `threading`, `queue`, `json`, `pathlib`, and `tkinter`.

### AI development tools

- **OpenAI Codex:** used as a development and maintenance assistant. The application does not call AI APIs at runtime and does not require an API key.

## 📦 Requirements and installation

### Requirements

- Windows 10/11 (the instructions below are for Windows).
- Python 3.8+ installed with Tcl/Tk.
- Git.
- Yaesu FTX-1 connected to the computer by USB using the **Enhanced COM Port (CAT-1)**.
- The radio's CAT-1 baud rate must match the application setting; the factory default is 38400 bps.

### Clone and install

Open PowerShell in the folder where you want to store the project:

```powershell
git clone https://github.com/evertonma/FTX-1CAT_PR2EM.git
cd FTX-1CAT_PR2EM
py -m venv .venv
```

Install the dependency inside the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the application:

```powershell
.\.venv\Scripts\python.exe ftx1_cat_menu.py
```

These commands do not require activating the virtual environment with `Activate.ps1`, avoiding PowerShell script execution policy issues.

### `.env` configuration

No `.env` file or environment variables are required. The application uses no credentials, tokens, or external services. It configures Tcl/Tk paths automatically when available in the Python installation.

## 💻 How to use

1. Connect and power on the FTX-1.
2. Start the application. If detected, the CP2105 Enhanced COM Port is selected automatically.
3. Check the CAT-1 baud rate and click **Connect**. Wait for radio identification and the initial control readings.
4. In **Quick Controls**, use the on-screen dial or click the MAIN frequency display to enter a frequency. The display also follows changes made with the radio's physical dial.
5. Click a band button to request that band from the radio. With **BAND STACK** enabled on the FTX-1, the radio recalls the frequency and mode stored in its Band Stack.
6. Adjust the sliders to send RF POWER, D-LEVEL, D-PEAK, NB, DNR, or CH-STEP changes.
7. To read or change other settings, open **CAT Menu**, choose a group, and use **Read**, **Write**, or the batch read/write commands.
8. Use **Save Backup…** before larger changes. Restore compares values first and asks for confirmation before writing.

### Frequency entry examples

Type digits without separators; punctuation is applied automatically.

| Input | Frequency sent |
| --- | --- |
| `1448` | `144.800.000 Hz` |
| `27555` | `27.555.000 Hz` |

### Troubleshooting

- If the port does not appear, check the USB connection and refresh the port list.
- The application looks for `CP2105` and `Enhanced` in the port description. If the driver uses a different name, select the CAT-1 port manually.
- If the radio does not respond, check that **Enhanced COM Port (CAT-1)** is selected, the baud rate matches `CAT-1 RATE`, and no other application has opened the port.
- If Tkinter fails to start, install or repair Python with Tcl/Tk included.
- Band selection depends on **BAND STACK** being enabled on the radio.

## 🧭 Simplified workflow

```text
Start application
  → locate CAT-1 port
  → open serial connection and identify radio
  → read frequency, mode, and quick controls
  → send CAT commands as controls change
  → query radio again and refresh the interface
```

Serial reads and writes run in the background to keep the interface responsive.

## 🗂️ Project structure

```text
FTX-1CAT_PR2EM/
├── ftx1_cat_menu.py   # Tkinter interface and CAT operations
├── ftx1_menu.py       # EX menu item table and serial CAT transport
├── requirements.txt   # Python dependencies
├── LICENSE            # PolyForm Noncommercial License 1.0.0
└── README.md          # This documentation
```

## 🤝 Contributing

1. Fork the repository.
2. Create a branch for your change: `git switch -c feature/my-improvement`.
3. Keep changes focused. For new CAT commands, include the corresponding FTX-1 manual reference.
4. Before opening a pull request, check Python syntax and, when possible, test with a radio or a simulated serial interface.
5. Include a behavior summary, reproduction steps, and screenshots for interface changes.

Do not include personal backups, radio configuration files, virtual environments, or documents that cannot be redistributed. Contributions are subject to the project's noncommercial license unless the copyright holder agrees otherwise in writing.

## 📄 License

This software is licensed under the **PolyForm Noncommercial License 1.0.0**. It permits use, modification, and redistribution for noncommercial purposes. Commercial use requires separate permission from the copyright holder. See [LICENSE](LICENSE) and the [official license text](https://polyformproject.org/licenses/noncommercial/1.0.0/). This is a source-available license, not an OSI-approved open-source license.

## 👤 Credits

Developed by **Everton Machado — PR2EM**, with assistance from **OpenAI Codex**.

---

# Versão em Português

## Yaesu FTX-1 CAT Menu — by PR2EM

> Aplicativo desktop em Python para consultar e controlar o transceptor Yaesu FTX-1 pela interface serial CAT. Reúne controles rápidos de operação, seleção de banda e gerenciamento dos parâmetros do menu CAT.

> **Versão:** 0.1 Alfa. O projeto está em desenvolvimento. Tenha cuidado ao gravar configurações no rádio.

## 🚀 Funcionalidades

- **Conexão CAT:** detecta e seleciona automaticamente a porta `Enhanced COM Port` do adaptador Silicon Labs CP2105 quando disponível. A conexão é aberta quando você clica em **Connect**.
- **Identificação do rádio:** lê o ID do rádio e a versão do firmware MAIN após a conexão.
- **Sintonia MAIN:** exibe a frequência atual e acompanha periodicamente alterações feitas pelo dial físico do rádio.
- **Entrada direta de frequência:** aceita números abreviados e aplica separadores automaticamente; por exemplo, `1448` se torna `144.800.000 Hz` e `27555` se torna `27.555.000 Hz`.
- **Dial na interface:** altera a frequência com o scroll do mouse.
- **Seleção de banda:** botões solicitam a seleção de banda via CAT e usam o Band Stack interno do rádio, sem enviar uma frequência fixa. Como a lista CAT Band Select não tem uma entrada para 11 m, o botão **11m** sintoniza diretamente em 27,555 MHz (frequência de chamada DX), mantendo o modo atual.
- **Seleção de modo:** botões selecionam os modos MAIN disponíveis.
- **CH-STEP:** slider vertical que se adapta ao modo atual e aceita arraste, clique na escala e ajuste pelo scroll do mouse.
- **Controles rápidos:** sliders ajustam RF POWER, D-LEVEL, D-PEAK, NB e DNR e enviam as alterações durante o ajuste.
- **Parâmetros FUNC:** permite escolher localmente um parâmetro para ajustar sem alterar a função atribuída ao botão físico FUNC do rádio.
- **Menu CAT:** pesquisa e lê itens do menu; os itens compatíveis podem ser gravados individualmente ou em lote.
- **Backup e restauração:** salva configurações lidas em JSON e compara um backup com o estado atual antes de restaurar valores compatíveis.
- **Registro de comunicação:** informa o andamento das operações e pode exibir os comandos CAT enviados e recebidos.

## 🛠️ Tecnologias e recursos

### Linguagem

- Python 3.8 ou superior.

### Bibliotecas e frameworks

- **Tkinter / ttk:** interface gráfica.
- **pyserial 3.5:** descoberta de portas seriais e comunicação CAT.
- **Biblioteca padrão do Python:** incluindo `threading`, `queue`, `json`, `pathlib` e `tkinter`.

### Ferramentas de IA no desenvolvimento

- **OpenAI Codex:** utilizado como assistente de desenvolvimento e manutenção. O aplicativo não chama APIs de IA durante a execução e não exige chave de API.

## 📦 Pré-requisitos e instalação

### Pré-requisitos

- Windows 10/11 (as instruções abaixo são para Windows).
- Python 3.8+ instalado com Tcl/Tk.
- Git.
- Yaesu FTX-1 conectado ao computador por USB usando a **Enhanced COM Port (CAT-1)**.
- A taxa CAT-1 do rádio deve corresponder à selecionada no programa; o padrão de fábrica é 38400 bps.

### Clonar e instalar

Abra o PowerShell na pasta onde deseja guardar o projeto:

```powershell
git clone https://github.com/evertonma/FTX-1CAT_PR2EM.git
cd FTX-1CAT_PR2EM
py -m venv .venv
```

Instale a dependência dentro do ambiente virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inicie o aplicativo:

```powershell
.\.venv\Scripts\python.exe ftx1_cat_menu.py
```

Esses comandos não exigem ativar o ambiente virtual com `Activate.ps1`, evitando problemas com a política de execução de scripts do PowerShell.

### Configuração de `.env`

Não é necessário criar um arquivo `.env` nem configurar variáveis de ambiente. O aplicativo não usa credenciais, tokens ou serviços externos. Ele configura os caminhos do Tcl/Tk automaticamente quando disponíveis na instalação do Python.

## 💻 Como usar

1. Conecte o FTX-1 ao computador e ligue o rádio.
2. Inicie o aplicativo. Se detectada, a porta CP2105 Enhanced COM Port será selecionada automaticamente.
3. Confira a taxa CAT-1 e clique em **Connect**. Aguarde a identificação do rádio e a leitura inicial dos controles.
4. Na aba **Quick Controls**, use o dial na tela ou clique no display de frequência MAIN para digitar uma frequência. O display também acompanha alterações feitas pelo dial físico do rádio.
5. Clique em um botão de banda para solicitá-la ao rádio. Com **BAND STACK** habilitado no FTX-1, o rádio recupera a frequência e o modo armazenados no Band Stack.
6. Ajuste os sliders para enviar alterações de RF POWER, D-LEVEL, D-PEAK, NB, DNR ou CH-STEP.
7. Para ler ou alterar outros ajustes, abra **CAT Menu**, escolha um grupo e use **Read**, **Write** ou os comandos de leitura/gravação em lote.
8. Use **Save Backup…** antes de alterações maiores. A restauração compara os valores primeiro e pede confirmação antes de gravar.

### Exemplos de entrada de frequência

Digite os números sem separadores; a pontuação é aplicada automaticamente.

| Entrada | Frequência enviada |
| --- | --- |
| `1448` | `144.800.000 Hz` |
| `27555` | `27.555.000 Hz` |

### Diagnóstico rápido

- Se a porta não aparecer, confira a conexão USB e atualize a lista de portas.
- O aplicativo procura `CP2105` e `Enhanced` na descrição da porta. Se o driver mostrar outro nome, selecione manualmente a porta CAT-1.
- Se o rádio não responder, confirme a **Enhanced COM Port (CAT-1)**, a taxa correspondente a `CAT-1 RATE` e que nenhum outro aplicativo está usando a porta.
- Se o Tkinter não iniciar, instale ou repare o Python incluindo Tcl/Tk.
- A seleção de banda depende de **BAND STACK** estar habilitado no rádio.

## 🧭 Fluxo simplificado

```text
Iniciar aplicativo
  → localizar a porta CAT-1
  → abrir a conexão serial e identificar o rádio
  → ler frequência, modo e controles rápidos
  → enviar comandos CAT durante os ajustes
  → consultar novamente o rádio e atualizar a interface
```

As leituras e gravações seriais são executadas em segundo plano para manter a interface responsiva.

## 🗂️ Estrutura do projeto

```text
FTX-1CAT_PR2EM/
├── ftx1_cat_menu.py   # Interface Tkinter e operações CAT
├── ftx1_menu.py       # Tabela de itens do menu EX e comunicação serial CAT
├── requirements.txt   # Dependências Python
├── LICENSE            # PolyForm Noncommercial License 1.0.0
└── README.md          # Esta documentação
```

## 🤝 Como contribuir

1. Faça um fork do repositório.
2. Crie uma branch para sua alteração: `git switch -c feature/minha-melhoria`.
3. Mantenha as alterações objetivas. Para novos comandos CAT, inclua a referência correspondente ao manual do FTX-1.
4. Antes de abrir um pull request, confira a sintaxe Python e, quando possível, teste com um rádio ou uma interface serial simulada.
5. Inclua um resumo do comportamento, passos para reproduzir e capturas de tela para alterações na interface.

Não inclua backups pessoais, arquivos de configuração do rádio, ambientes virtuais ou documentos que não possam ser redistribuídos. As contribuições seguem a licença não comercial do projeto, salvo autorização diferente por escrito do titular dos direitos autorais.

## 📄 Licença

Este software está licenciado sob a **PolyForm Noncommercial License 1.0.0**. Ela permite uso, modificação e redistribuição para fins não comerciais. O uso comercial exige autorização separada do titular dos direitos autorais. Consulte o arquivo [LICENSE](LICENSE) e o [texto oficial da licença](https://polyformproject.org/licenses/noncommercial/1.0.0/). Esta é uma licença de código-fonte disponível, mas não aprovada pela OSI como licença open source.

## 👤 Créditos

Desenvolvido por **Everton Machado — PR2EM**, com assistência do **OpenAI Codex**.

