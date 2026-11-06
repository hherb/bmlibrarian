//! Choosing the private server's TCP port.
//!
//! The port is fixed by default and moves upward only when taken, skipping the
//! ports other PostgreSQL servers and poolers commonly use, so a PostgreSQL
//! installed later on this machine never collides with ours.

use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::ops::RangeInclusive;
use std::time::Duration;

/// The port tried first for the private server.
pub const DEFAULT_PORT: u16 = 5418;

/// Port ranges other PostgreSQL servers and poolers commonly use: the default
/// 5432 and the ports next to it used by side-by-side installs, the owner's
/// development PostgreSQL 18 (5532), and pgbouncer (6432, 6543).
const AVOIDED_RANGES: [RangeInclusive<u16>; 4] =
    [5432..=5439, 5532..=5532, 6432..=6432, 6543..=6543];

/// First port of the OS ephemeral range, where ports are handed out to
/// outgoing connections and so may be taken at any moment.
pub const EPHEMERAL_START: u16 = 49152;

/// Why no port could be chosen.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum PortError {
    /// Every candidate from `start` up to the ephemeral range was taken.
    #[error("no free port from {start} up to {EPHEMERAL_START}")]
    NoFreePort {
        /// The port the scan started from.
        start: u16,
    },
}

/// Whether `port` must never be used for the private server.
pub fn is_avoided(port: u16) -> bool {
    port >= EPHEMERAL_START || AVOIDED_RANGES.iter().any(|r| r.contains(&port))
}

/// The first port from `start` upward that is not avoided and `is_free`.
pub fn choose_port(start: u16, is_free: impl Fn(u16) -> bool) -> Result<u16, PortError> {
    (start..EPHEMERAL_START)
        .find(|&p| !is_avoided(p) && is_free(p))
        .ok_or(PortError::NoFreePort { start })
}

/// How long a connection probe waits; loopback refusals are immediate.
const PROBE_TIMEOUT: Duration = Duration::from_millis(200);

/// Whether nothing is listening on `127.0.0.1:port` right now.
///
/// Binding alone is not enough: on macOS/BSD a loopback bind succeeds while
/// another process listens on the wildcard address (e.g. a Docker port
/// mapping), so a connection attempt must also be refused. (Binding the
/// wildcard address instead would raise a Windows firewall prompt.)
pub fn port_is_free(port: u16) -> bool {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    TcpListener::bind(addr).is_ok() && TcpStream::connect_timeout(&addr, PROBE_TIMEOUT).is_err()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn avoided_ports() {
        for p in [5432, 5435, 5439, 5532, 6432, 6543, 49152, 60000] {
            assert!(is_avoided(p), "{p} should be avoided");
        }
        for p in [5418, 5431, 5440, 5531] {
            assert!(!is_avoided(p), "{p} should not be avoided");
        }
    }

    #[test]
    fn default_when_free() {
        assert_eq!(choose_port(DEFAULT_PORT, |_| true), Ok(5418));
    }

    #[test]
    fn skips_taken() {
        assert_eq!(
            choose_port(DEFAULT_PORT, |p| p != 5418 && p != 5419),
            Ok(5420)
        );
    }

    #[test]
    fn skips_avoided_while_scanning() {
        assert_eq!(choose_port(5430, |_| true), Ok(5430));
        assert_eq!(choose_port(5431, |p| p != 5431), Ok(5440));
    }

    #[test]
    fn exhausted() {
        assert_eq!(
            choose_port(49150, |_| false),
            Err(PortError::NoFreePort { start: 49150 })
        );
    }

    #[test]
    fn wildcard_listener_is_taken() {
        let listener = TcpListener::bind("0.0.0.0:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(!port_is_free(port));
    }

    #[test]
    fn real_bind() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(!port_is_free(port));
    }
}
