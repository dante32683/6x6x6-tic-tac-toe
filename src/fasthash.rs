//! A fast hasher for the search's hash maps. The keys are bit sets and packed
//! small integers chosen by the search itself, not by an adversary, so the
//! std SipHash's flood resistance buys nothing; profiling on 2026-11-19 put
//! SipHash at 11% of leaf-check time. This is the FxHash scheme rustc uses:
//! rotate, xor in each word, multiply.

use std::hash::{BuildHasherDefault, Hasher};

#[derive(Default, Clone, Copy)]
pub struct FxHasher(u64);

/// FxHash's multiplier (from Firefox's hash, used by rustc-hash).
const SEED: u64 = 0x51_7c_c1_b7_27_22_0a_95;

impl FxHasher {
    fn add(&mut self, w: u64) {
        self.0 = (self.0.rotate_left(5) ^ w).wrapping_mul(SEED);
    }
}

impl Hasher for FxHasher {
    fn write(&mut self, bytes: &[u8]) {
        for chunk in bytes.chunks(8) {
            let mut w = [0u8; 8];
            w[..chunk.len()].copy_from_slice(chunk);
            self.add(u64::from_le_bytes(w));
        }
    }
    fn write_u8(&mut self, i: u8) {
        self.add(i as u64);
    }
    fn write_u16(&mut self, i: u16) {
        self.add(i as u64);
    }
    fn write_u32(&mut self, i: u32) {
        self.add(i as u64);
    }
    fn write_u64(&mut self, i: u64) {
        self.add(i);
    }
    fn write_usize(&mut self, i: usize) {
        self.add(i as u64);
    }
    fn finish(&self) -> u64 {
        // the multiply leaves the low bits poorly mixed, and hashbrown picks
        // buckets from them; rustc-hash 2 rotates the same way
        self.0.rotate_left(26)
    }
}

pub type FxBuild = BuildHasherDefault<FxHasher>;
pub type FxDashMap<K, V> = dashmap::DashMap<K, V, FxBuild>;
pub type FxHashSet<K> = std::collections::HashSet<K, FxBuild>;
pub type FxHashMap<K, V> = std::collections::HashMap<K, V, FxBuild>;
