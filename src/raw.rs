// Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
// SPDX-License-Identifier: MIT OR Apache-2.0
//
// ferogram is a high-performance Telegram MTProto framework written in Rust.
// ferogram-py provides Python bindings built on top of the Rust core for
// building Telegram clients, bots, and applications with a simple API.
//
// Rust core: https://github.com/ankit-chaubey/ferogram
// Python bindings: https://github.com/ankit-chaubey/ferogram-py
//
// If you use or modify this code, keep this notice at the top of the file
// and include the LICENSE-MIT or LICENSE-APACHE file from this repository.

// Raw TL invoke: Python passes serialized TL bytes, Rust sends via MTProto,
// returns raw response bytes. Python handles ser/de on both ends.
//
// Use ferogram::tl for all TL traits to avoid a duplicate-crate version
// conflict with ferogram's internal copy of ferogram-tl-types.

use ferogram::tl::{RemoteCall, Serializable, Deserializable, Cursor};
use pyo3::prelude::*;

use crate::py_err;

struct RawCall(Vec<u8>);

impl Serializable for RawCall {
    fn serialize(&self, buf: &mut impl Extend<u8>) {
        buf.extend(self.0.iter().copied());
    }
}

impl RemoteCall for RawCall {
    type Return = RawBytes;
}

struct RawBytes(Vec<u8>);

impl Deserializable for RawBytes {
    fn deserialize(buf: &mut Cursor<'_>) -> ferogram::tl::deserialize::Result<Self> {
        let mut out = Vec::new();
        buf.read_to_end(&mut out);
        Ok(RawBytes(out))
    }
}

pub async fn invoke_raw_inner(
    client: &ferogram::Client,
    tl_bytes: Vec<u8>,
) -> PyResult<Vec<u8>> {
    let call = RawCall(tl_bytes);
    let result = client.invoke(&call).await.map_err(py_err)?;
    Ok(result.0)
}
