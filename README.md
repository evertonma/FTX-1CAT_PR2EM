# Yaesu FTX-1 CAT Menu â€” by PR2EM

# VersÃ£o em PortuguÃªs abaixo

![Status: v0.1 Alpha](https://img.shields.io/badge/status-v0.1--alpha-orange)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blueviolet)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey)

> A Python desktop application for reading and controlling the Yaesu FTX-1 transceiver through its serial CAT interface. It brings together quick operating controls, band selection, and CAT menu parameter management.

> **Version:** 0.1 Alpha. This project is under development. Use care when writing settings to your radio.

## ðŸš€ Features

- **CAT connection:** automatically detects and selects the Silicon Labs CP2105 `Enhanced COM Port` when available. The connection opens after you click **Connect**.
- **Radio identification:** reads the radio ID and MAIN firmware version after connecting.
- **MAIN tuning:** displays the current frequency and periodically tracks changes made with the radio's physical dial.
- **Direct frequency entry:** accepts abbreviated numeric input and applies separators automatically; for example, `1448` becomes `144.800.000 Hz` and `27555` becomes `27.555.000 Hz`.
- **On-screen dial:** changes frequency with the mouse wheel.
- **Band selection:** buttons request the FTX-1 CAT band selection and use the radio's internal Band Stack rather than sending a fixed frequency.
- **Mode selection:** buttons select available MAIN operating modes.
- **CH-STEP:** a vertical slider adapts to the current mode and supports dragging, clicking the scale, and mouse wheel adjustment.
- **Quick controls:** sliders adjust RF POWER, D-LEVEL, D-PEAK, NB, and DNR and send changes while you adjust them.
- **FUNC parameters:** select a parameter to adjust locally without changing the assignment of the radio's physical FUNC button.
- **CAT menu:** search and read menu items; supported items can be written individually or in batches.
- **Backup and restore:** saves read settings to JSON and compares a backup with the current state before restoring compatible values.
- **Communication log:** reports operation progress and can show CAT commands sent and received.

## ðŸ› ï¸ Technologies and resources

### Language

- Python 3.8 or newer.

### Libraries and frameworks

- **Tkinter / ttk:** graphical interface.
- **pyserial 3.5:** serial port discovery and CAT communication.
- **Python standard library:** including `threading`, `queue`, `json`, `pathlib`, and `tkinter`.

### AI development tools

- **OpenAI Codex:** used as a development and maintenance assistant. The application does not call AI APIs at runtime and does not require an API key.

## ðŸ“¦ Requirements and installation

### Requirements

- Windows 10/11 (the instructions below are for Windows).
- Python 3.8+ installed with Tcl/Tk.
- Git.
- Yaesu FTX-1 connected to the computer by USB using the **Enhanced COM Port (CAT-1)**.
- The radio's CAT-1 baud rate must match the application setting; the factory default is 38400 bps.

### Clone and install

Open PowerShell in the folder where you want to store the project:

```powershell
git clone https://github.com/evertonma/pr2em_ham.git
cd pr2em_ham
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

## ðŸ’» How to use

1. Connect and power on the FTX-1.
2. Start the application. If detected, the CP2105 Enhanced COM Port is selected automatically.
3. Check the CAT-1 baud rate and click **Connect**. Wait for radio identification and the initial control readings.
4. In **Quick Controls**, use the on-screen dial or click the MAIN frequency display to enter a frequency. The display also follows changes made with the radio's physical dial.
5. Click a band button to request that band from the radio. With **BAND STACK** enabled on the FTX-1, the radio recalls the frequency and mode stored in its Band Stack.
6. Adjust the sliders to send RF POWER, D-LEVEL, D-PEAK, NB, DNR, or CH-STEP changes.
7. To read or change other settings, open **CAT Menu**, choose a group, and use **Read**, **Write**, or the batch read/write commands.
8. Use **Save Backupâ€¦** before larger changes. Restore compares values first and asks for confirmation before writing.

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

## ðŸ§­ Simplified workflow

```text
Start application
  â†’ locate CAT-1 port
  â†’ open serial connection and identify radio
  â†’ read frequency, mode, and quick controls
  â†’ send CAT commands as controls change
  â†’ query radio again and refresh the interface
```

Serial reads and writes run in the background to keep the interface responsive.

## ðŸ—‚ï¸ Project structure

```text
pr2em_ham/
â”œâ”€â”€ ftx1_cat_menu.py   # Tkinter interface and CAT operations
â”œâ”€â”€ ftx1_menu.py       # EX menu item table and serial CAT transport
â”œâ”€â”€ requirements.txt   # Python dependencies
â”œâ”€â”€ LICENSE            # PolyForm Noncommercial License 1.0.0
â””â”€â”€ README.md          # This documentation
```

## ðŸ¤ Contributing

1. Fork the repository.
2. Create a branch for your change: `git switch -c feature/my-improvement`.
3. Keep changes focused. For new CAT commands, include the corresponding FTX-1 manual reference.
4. Before opening a pull request, check Python syntax and, when possible, test with a radio or a simulated serial interface.
5. Include a behavior summary, reproduction steps, and screenshots for interface changes.

Do not include personal backups, radio configuration files, virtual environments, or documents that cannot be redistributed. Contributions are subject to the project's noncommercial license unless the copyright holder agrees otherwise in writing.

## ðŸ“„ License

This software is licensed under the **PolyForm Noncommercial License 1.0.0**. It permits use, modification, and redistribution for noncommercial purposes. Commercial use requires separate permission from the copyright holder. See [LICENSE](LICENSE) and the [official license text](https://polyformproject.org/licenses/noncommercial/1.0.0/). This is a source-available license, not an OSI-approved open-source license.

## ðŸ‘¤ Credits

Developed by **Everton Machado â€” PR2EM**, with assistance from **OpenAI Codex**.

---

# Yaesu FTX-1 CAT Menu â€” by PR2EM (PortuguÃªs)

> Aplicativo desktop em Python para consultar e controlar o transceptor Yaesu FTX-1 pela interface serial CAT. ReÃºne controles rÃ¡pidos de operaÃ§Ã£o, seleÃ§Ã£o de banda e gerenciamento dos parÃ¢metros do menu CAT.

> **VersÃ£o:** 0.1 Alfa. O projeto estÃ¡ em desenvolvimento. Tenha cuidado ao gravar configuraÃ§Ãµes no rÃ¡dio.

## ðŸš€ Funcionalidades

- **ConexÃ£o CAT:** detecta e seleciona automaticamente a porta `Enhanced COM Port` do adaptador Silicon Labs CP2105 quando disponÃ­vel. A conexÃ£o Ã© aberta quando vocÃª clica em **Connect**.
- **IdentificaÃ§Ã£o do rÃ¡dio:** lÃª o ID do rÃ¡dio e a versÃ£o do firmware MAIN apÃ³s a conexÃ£o.
- **Sintonia MAIN:** exibe a frequÃªncia atual e acompanha periodicamente alteraÃ§Ãµes feitas pelo dial fÃ­sico do rÃ¡dio.
- **Entrada direta de frequÃªncia:** aceita nÃºmeros abreviados e aplica separadores automaticamente; por exemplo, `1448` se torna `144.800.000 Hz` e `27555` se torna `27.555.000 Hz`.
- **Dial na interface:** altera a frequÃªncia com o scroll do mouse.
- **SeleÃ§Ã£o de banda:** botÃµes solicitam a seleÃ§Ã£o de banda via CAT e usam o Band Stack interno do rÃ¡dio, sem enviar uma frequÃªncia fixa.
- **SeleÃ§Ã£o de modo:** botÃµes selecionam os modos MAIN disponÃ­veis.
- **CH-STEP:** slider vertical que se adapta ao modo atual e aceita arraste, clique na escala e ajuste pelo scroll do mouse.
- **Controles rÃ¡pidos:** sliders ajustam RF POWER, D-LEVEL, D-PEAK, NB e DNR e enviam as alteraÃ§Ãµes durante o ajuste.
- **ParÃ¢metros FUNC:** permite escolher localmente um parÃ¢metro para ajustar sem alterar a funÃ§Ã£o atribuÃ­da ao botÃ£o fÃ­sico FUNC do rÃ¡dio.
- **Menu CAT:** pesquisa e lÃª itens do menu; os itens compatÃ­veis podem ser gravados individualmente ou em lote.
- **Backup e restauraÃ§Ã£o:** salva configuraÃ§Ãµes lidas em JSON e compara um backup com o estado atual antes de restaurar valores compatÃ­veis.
- **Registro de comunicaÃ§Ã£o:** informa o andamento das operaÃ§Ãµes e pode exibir os comandos CAT enviados e recebidos.

## ðŸ› ï¸ Tecnologias e recursos

### Linguagem

- Python 3.8 ou superior.

### Bibliotecas e frameworks

- **Tkinter / ttk:** interface grÃ¡fica.
- **pyserial 3.5:** descoberta de portas seriais e comunicaÃ§Ã£o CAT.
- **Biblioteca padrÃ£o do Python:** incluindo `threading`, `queue`, `json`, `pathlib` e `tkinter`.

### Ferramentas de IA no desenvolvimento

- **OpenAI Codex:** utilizado como assistente de desenvolvimento e manutenÃ§Ã£o. O aplicativo nÃ£o chama APIs de IA durante a execuÃ§Ã£o e nÃ£o exige chave de API.

## ðŸ“¦ PrÃ©-requisitos e instalaÃ§Ã£o

### PrÃ©-requisitos

- Windows 10/11 (as instruÃ§Ãµes abaixo sÃ£o para Windows).
- Python 3.8+ instalado com Tcl/Tk.
- Git.
- Yaesu FTX-1 conectado ao computador por USB usando a **Enhanced COM Port (CAT-1)**.
- A taxa CAT-1 do rÃ¡dio deve corresponder Ã  selecionada no programa; o padrÃ£o de fÃ¡brica Ã© 38400 bps.

### Clonar e instalar

Abra o PowerShell na pasta onde deseja guardar o projeto:

```powershell
git clone https://github.com/evertonma/pr2em_ham.git
cd pr2em_ham
py -m venv .venv
```

Instale a dependÃªncia dentro do ambiente virtual:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inicie o aplicativo:

```powershell
.\.venv\Scripts\python.exe ftx1_cat_menu.py
```

Esses comandos nÃ£o exigem ativar o ambiente virtual com `Activate.ps1`, evitando problemas com a polÃ­tica de execuÃ§Ã£o de scripts do PowerShell.

### ConfiguraÃ§Ã£o de `.env`

NÃ£o Ã© necessÃ¡rio criar um arquivo `.env` nem configurar variÃ¡veis de ambiente. O aplicativo nÃ£o usa credenciais, tokens ou serviÃ§os externos. Ele configura os caminhos do Tcl/Tk automaticamente quando disponÃ­veis na instalaÃ§Ã£o do Python.

## ðŸ’» Como usar

1. Conecte o FTX-1 ao computador e ligue o rÃ¡dio.
2. Inicie o aplicativo. Se detectada, a porta CP2105 Enhanced COM Port serÃ¡ selecionada automaticamente.
3. Confira a taxa CAT-1 e clique em **Connect**. Aguarde a identificaÃ§Ã£o do rÃ¡dio e a leitura inicial dos controles.
4. Na aba **Quick Controls**, use o dial na tela ou clique no display de frequÃªncia MAIN para digitar uma frequÃªncia. O display tambÃ©m acompanha alteraÃ§Ãµes feitas pelo dial fÃ­sico do rÃ¡dio.
5. Clique em um botÃ£o de banda para solicitÃ¡-la ao rÃ¡dio. Com **BAND STACK** habilitado no FTX-1, o rÃ¡dio recupera a frequÃªncia e o modo armazenados no Band Stack.
6. Ajuste os sliders para enviar alteraÃ§Ãµes de RF POWER, D-LEVEL, D-PEAK, NB, DNR ou CH-STEP.
7. Para ler ou alterar outros ajustes, abra **CAT Menu**, escolha um grupo e use **Read**, **Write** ou os comandos de leitura/gravaÃ§Ã£o em lote.
8. Use **Save Backupâ€¦** antes de alteraÃ§Ãµes maiores. A restauraÃ§Ã£o compara os valores primeiro e pede confirmaÃ§Ã£o antes de gravar.

### Exemplos de entrada de frequÃªncia

Digite os nÃºmeros sem separadores; a pontuaÃ§Ã£o Ã© aplicada automaticamente.

| Entrada | FrequÃªncia enviada |
| --- | --- |
| `1448` | `144.800.000 Hz` |
| `27555` | `27.555.000 Hz` |

### DiagnÃ³stico rÃ¡pido

- Se a porta nÃ£o aparecer, confira a conexÃ£o USB e atualize a lista de portas.
- O aplicativo procura `CP2105` e `Enhanced` na descriÃ§Ã£o da porta. Se o driver mostrar outro nome, selecione manualmente a porta CAT-1.
- Se o rÃ¡dio nÃ£o responder, confirme a **Enhanced COM Port (CAT-1)**, a taxa correspondente a `CAT-1 RATE` e que nenhum outro aplicativo estÃ¡ usando a porta.
- Se o Tkinter nÃ£o iniciar, instale ou repare o Python incluindo Tcl/Tk.
- A seleÃ§Ã£o de banda depende de **BAND STACK** estar habilitado no rÃ¡dio.

## ðŸ§­ Fluxo simplificado

```text
Iniciar aplicativo
  â†’ localizar a porta CAT-1
  â†’ abrir a conexÃ£o serial e identificar o rÃ¡dio
  â†’ ler frequÃªncia, modo e controles rÃ¡pidos
  â†’ enviar comandos CAT durante os ajustes
  â†’ consultar novamente o rÃ¡dio e atualizar a interface
```

As leituras e gravaÃ§Ãµes seriais sÃ£o executadas em segundo plano para manter a interface responsiva.

## ðŸ—‚ï¸ Estrutura do projeto

```text
pr2em_ham/
â”œâ”€â”€ ftx1_cat_menu.py   # Interface Tkinter e operaÃ§Ãµes CAT
â”œâ”€â”€ ftx1_menu.py       # Tabela de itens do menu EX e comunicaÃ§Ã£o serial CAT
â”œâ”€â”€ requirements.txt   # DependÃªncias Python
â”œâ”€â”€ LICENSE            # PolyForm Noncommercial License 1.0.0
â””â”€â”€ README.md          # Esta documentaÃ§Ã£o
```

## ðŸ¤ Como contribuir

1. FaÃ§a um fork do repositÃ³rio.
2. Crie uma branch para sua alteraÃ§Ã£o: `git switch -c feature/minha-melhoria`.
3. Mantenha as alteraÃ§Ãµes objetivas. Para novos comandos CAT, inclua a referÃªncia correspondente ao manual do FTX-1.
4. Antes de abrir um pull request, confira a sintaxe Python e, quando possÃ­vel, teste com um rÃ¡dio ou uma interface serial simulada.
5. Inclua um resumo do comportamento, passos para reproduzir e capturas de tela para alteraÃ§Ãµes na interface.

NÃ£o inclua backups pessoais, arquivos de configuraÃ§Ã£o do rÃ¡dio, ambientes virtuais ou documentos que nÃ£o possam ser redistribuÃ­dos. As contribuiÃ§Ãµes seguem a licenÃ§a nÃ£o comercial do projeto, salvo autorizaÃ§Ã£o diferente por escrito do titular dos direitos autorais.

## ðŸ“„ LicenÃ§a

Este software estÃ¡ licenciado sob a **PolyForm Noncommercial License 1.0.0**. Ela permite uso, modificaÃ§Ã£o e redistribuiÃ§Ã£o para fins nÃ£o comerciais. O uso comercial exige autorizaÃ§Ã£o separada do titular dos direitos autorais. Consulte o arquivo [LICENSE](LICENSE) e o [texto oficial da licenÃ§a](https://polyformproject.org/licenses/noncommercial/1.0.0/). Esta Ã© uma licenÃ§a de cÃ³digo-fonte disponÃ­vel, mas nÃ£o aprovada pela OSI como licenÃ§a open source.

## ðŸ‘¤ CrÃ©ditos

Desenvolvido por **Everton Machado â€” PR2EM**, com assistÃªncia do **OpenAI Codex**.

