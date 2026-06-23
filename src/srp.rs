// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
//
// ferogram: async Telegram MTProto client in Rust
// https://github.com/ankit-chaubey/ferogram
//
// Licensed under either the MIT License or the Apache License 2.0.
// See the LICENSE-MIT or LICENSE-APACHE file in this repository:
// https://github.com/ankit-chaubey/ferogram
//
// Feel free to use, modify, and share this code.
// Please keep this notice when redistributing.

use ferogram_crypto::srp;
use pyo3::prelude::*;

use crate::py_err;

#[pyfunction]
pub fn srp_calculate(
    salt1: Vec<u8>,
    salt2: Vec<u8>,
    p: Vec<u8>,
    g: i32,
    srp_b: Vec<u8>,
    password: String,
) -> PyResult<(Vec<u8>, Vec<u8>)> {
    use std::io::Read;
    let mut a = [0u8; 256];
    std::fs::File::open("/dev/urandom")
        .and_then(|mut f| f.read_exact(&mut a))
        .map_err(py_err)?;

    let (m1, g_a) = srp::calculate_2fa(&salt1, &salt2, &p, g, &srp_b, &a, password.as_bytes())
        .map_err(py_err)?;

    Ok((g_a.to_vec(), m1.to_vec()))
}
