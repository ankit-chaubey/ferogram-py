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

use ferogram_tl_types::{Cursor, Deserializable, RemoteCall, Serializable};

// Wraps arbitrary pre-serialized TL bytes as a RemoteCall so they go through
// the full MTProto encrypted path (rpc_call), not rpc_call_raw.
pub struct RawCall(pub Vec<u8>);

impl Serializable for RawCall {
    fn serialize(&self, buf: &mut impl Extend<u8>) {
        buf.extend(self.0.iter().copied());
    }
}

impl RemoteCall for RawCall {
    type Return = RawBytes;
}

pub struct RawBytes(pub Vec<u8>);

impl Deserializable for RawBytes {
    fn deserialize(buf: &mut Cursor<'_>) -> ferogram_tl_types::deserialize::Result<Self> {
        let mut out = Vec::new();
        buf.read_to_end(&mut out);
        Ok(RawBytes(out))
    }
}
