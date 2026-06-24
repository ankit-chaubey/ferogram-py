// build.rs - regenerate ferogram/raw/generated/ from ferogram/api.tl
//
// Runs at `maturin develop` / `pip install .` time. Requires Python 3.9+ on
// PATH (the same interpreter maturin is already using to build the extension).
//
// To skip regen during development (e.g. you only changed Rust code):
//   FEROGRAM_SKIP_CODEGEN=1 maturin develop

use std::path::Path;
use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=ferogram/api.tl");
    println!("cargo:rerun-if-changed=ferogram/raw/codegen.py");
    println!("cargo:rerun-if-changed=build.rs");

    if std::env::var("FEROGRAM_SKIP_CODEGEN").is_ok() {
        return;
    }

    let manifest = std::env::var("CARGO_MANIFEST_DIR").unwrap();
    let tl_path = Path::new(&manifest).join("ferogram/api.tl");
    let out_dir = Path::new(&manifest).join("ferogram/raw/generated");
    let codegen = Path::new(&manifest).join("ferogram/raw/codegen.py");

    // Use the exact Python interpreter maturin chose (handles venvs, conda,
    // pyenv, and explicit PYO3_PYTHON overrides alike).
    let python = match pyo3_build_config::get().executable.clone() {
        Some(py) => py,
        None => {
            println!("cargo:warning=Skipping TL codegen: no Python executable found");
            return;
        }
    };

    let status = Command::new(&python)
        .args([
            codegen.to_str().unwrap(),
            tl_path.to_str().unwrap(),
            out_dir.to_str().unwrap(),
        ])
        .status()
        .unwrap_or_else(|e| {
            panic!("failed to launch codegen ({python:?}): {e}");
        });

    if !status.success() {
        panic!("codegen.py exited with {status}");
    }
}
