#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::{path::PathBuf, process::Stdio, time::Duration};
use tauri::{Manager, State};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::Mutex,
};

struct Bridge {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}

#[derive(Default)]
struct Backend(Mutex<Option<Bridge>>);

fn project_root() -> Result<PathBuf, String> {
    let mut candidates = Vec::new();
    if let Some(root) = std::env::var_os("MELIXSA_ROOT") {
        candidates.push(PathBuf::from(root));
    }
    if let Ok(exe) = std::env::current_exe() {
        candidates.extend(exe.ancestors().skip(1).take(8).map(PathBuf::from));
    }
    if let Ok(cwd) = std::env::current_dir() {
        candidates.extend(cwd.ancestors().take(5).map(PathBuf::from));
    }
    if cfg!(debug_assertions) {
        candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../.."));
    }
    candidates
        .into_iter()
        .find(|root| {
            root.join("Cogs/core/runtime.py").is_file()
                && root.join("MelixsaUI/backend/bridge.py").is_file()
        })
        .ok_or_else(|| {
            "Cartella Melixsa non trovata. Tieni MelixsaUI nel progetto o imposta MELIXSA_ROOT."
                .into()
        })
}

impl Bridge {
    fn spawn() -> Result<Self, String> {
        let root = project_root()?;
        let python = if cfg!(windows) {
            root.join(".venv/Scripts/python.exe")
        } else {
            root.join(".venv/bin/python")
        };
        if !python.is_file() {
            return Err("Ambiente Python assente. Crea .venv e installa requirements.txt nella cartella Melixsa.".into());
        }
        let mut command = Command::new(python);
        command
            .arg("-u")
            .arg(root.join("MelixsaUI/backend/bridge.py"))
            .current_dir(root)
            .env("PYTHONIOENCODING", "utf-8")
            .env("NO_COLOR", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let mut child = command
            .spawn()
            .map_err(|_| "Impossibile avviare il motore Python.".to_string())?;
        let input = child.stdin.take().ok_or("Canale Python non disponibile")?;
        let output = BufReader::new(
            child
                .stdout
                .take()
                .ok_or("Risposta Python non disponibile")?,
        );
        Ok(Self {
            child,
            input,
            output,
        })
    }

    async fn request(&mut self, method: &str, params: Value) -> Result<Value, String> {
        let mut request = serde_json::to_vec(&json!({"method": method, "params": params}))
            .map_err(|e| e.to_string())?;
        request.push(b'\n');
        self.input
            .write_all(&request)
            .await
            .map_err(|_| "Il motore Python si è arrestato.".to_string())?;
        self.input.flush().await.map_err(|e| e.to_string())?;
        let mut response = String::new();
        if self
            .output
            .read_line(&mut response)
            .await
            .map_err(|e| e.to_string())?
            == 0
        {
            return Err(
                "Motore Python non disponibile. Controlla le dipendenze di Melixsa.".into(),
            );
        }
        let response: Value = serde_json::from_str(&response)
            .map_err(|_| "Risposta del motore non valida.".to_string())?;
        if let Some(error) = response.get("error").and_then(Value::as_str) {
            return Err(error.into());
        }
        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    }
}

#[tauri::command]
async fn bridge_request(
    method: String,
    params: Option<Value>,
    backend: State<'_, Backend>,
) -> Result<Value, String> {
    if ![
        "snapshot",
        "command_catalog",
        "update_settings",
        "connect",
        "disconnect",
        "refresh_profile",
        "login_phone",
        "login_code",
        "login_password",
        "surveillance_overview",
        "surveillance_chats",
        "surveillance_set",
        "surveillance_logs",
        "stalk_overview",
        "stalk_set",
        "stalk_logs",
    ]
    .contains(&method.as_str())
    {
        return Err("Operazione non disponibile.".into());
    }
    let mut guard = backend.0.lock().await;
    if guard.is_none() {
        *guard = Some(Bridge::spawn()?);
    }
    let result = tokio::time::timeout(
        Duration::from_secs(90),
        guard
            .as_mut()
            .unwrap()
            .request(&method, params.unwrap_or(json!({}))),
    )
    .await;
    match result {
        Ok(result) => {
            if let Some(bridge) = guard.as_mut() {
                if bridge.child.try_wait().ok().flatten().is_some() {
                    *guard = None;
                }
            }
            result
        }
        Err(_) => {
            *guard = None;
            Err("Il motore non ha risposto. Riprova la connessione.".into())
        }
    }
}

fn main() {
    tauri::Builder::default()
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![bridge_request])
        .build(tauri::generate_context!())
        .expect("Impossibile aprire Melixsa")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                // EOF asks Python to stop services and flush pending writes before exit.
                tauri::async_runtime::block_on(async {
                    let backend = app.state::<Backend>();
                    let bridge = backend.0.lock().await.take();
                    if let Some(mut bridge) = bridge {
                        let _ = tokio::time::timeout(
                            Duration::from_secs(12),
                            bridge.request("shutdown", json!({})),
                        )
                        .await;
                        let _ = bridge.child.start_kill();
                    }
                });
            }
        });
}
