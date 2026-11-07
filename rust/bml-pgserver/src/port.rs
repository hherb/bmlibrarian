//! Choosing the private server's TCP port.
//!
//! The port is fixed by default and moves upward only when taken, skipping the
//! ports other PostgreSQL servers and poolers commonly use, so a PostgreSQL
//! installed later on this machine on a standard port never collides with
//! ours.

use std::io;
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
#[derive(Debug, thiserror::Error)]
pub enum PortError {
    /// Every candidate from `start` up to the ephemeral range was taken.
    #[error("no free port from {start} up to {EPHEMERAL_START}")]
    NoFreePort {
        /// The port the scan started from.
        start: u16,
    },
    /// A port could not be checked for another reason than being taken
    /// (e.g. a sandbox or firewall refusing the bind).
    #[error("cannot check whether port {port} on 127.0.0.1 is free: {source}")]
    Probe {
        /// The port being checked.
        port: u16,
        /// Why the check failed.
        source: io::Error,
    },
}

/// Whether `port` must never be used for the private server.
pub fn is_avoided(port: u16) -> bool {
    port >= EPHEMERAL_START || AVOIDED_RANGES.iter().any(|r| r.contains(&port))
}

/// The first port from `start` upward that is not avoided and `is_free`;
/// an error from `is_free` stops the scan.
pub fn choose_port(
    start: u16,
    is_free: impl Fn(u16) -> io::Result<bool>,
) -> Result<u16, PortError> {
    for port in (start..EPHEMERAL_START).filter(|&p| !is_avoided(p)) {
        if is_free(port).map_err(|source| PortError::Probe { port, source })? {
            return Ok(port);
        }
    }
    Err(PortError::NoFreePort { start })
}

/// How long a connection probe waits; loopback refusals are immediate.
const PROBE_TIMEOUT: Duration = Duration::from_millis(200);

/// Whether nothing is listening on `127.0.0.1:port` right now.
///
/// Binding alone is not enough: on macOS/BSD a loopback bind succeeds while
/// another process listens on the wildcard address (e.g. a Docker port
/// mapping), so a connection attempt must also be refused. (Binding the
/// wildcard address instead would raise a Windows firewall prompt.)
///
/// Only "address in use" means taken; any other bind error is returned, so
/// the real cause is reported instead of a scan that finds no free port.
pub fn port_is_free(port: u16) -> io::Result<bool> {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    match TcpListener::bind(addr) {
        Ok(listener) => drop(listener),
        Err(e) if is_taken(&e) => return Ok(false),
        Err(e) => return Err(e),
    }
    Ok(TcpStream::connect_timeout(&addr, PROBE_TIMEOUT).is_err())
}

/// Whether a bind error means another program holds the port.
fn is_taken(error: &io::Error) -> bool {
    // Windows refuses ports in its excluded ranges (Hyper-V, WSL) with
    // WSAEACCES: those are taken too, not a reason to stop.
    error.kind() == io::ErrorKind::AddrInUse
        || (cfg!(windows) && error.kind() == io::ErrorKind::PermissionDenied)
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

    /// `choose_port` with a probe that never fails.
    fn choose(start: u16, is_free: impl Fn(u16) -> bool) -> Result<u16, PortError> {
        choose_port(start, |p| Ok(is_free(p)))
    }

    #[test]
    fn default_when_free() {
        assert_eq!(choose(DEFAULT_PORT, |_| true).unwrap(), 5418);
    }

    #[test]
    fn skips_taken() {
        assert_eq!(
            choose(DEFAULT_PORT, |p| p != 5418 && p != 5419).unwrap(),
            5420
        );
    }

    #[test]
    fn skips_avoided_while_scanning() {
        assert_eq!(choose(5430, |_| true).unwrap(), 5430);
        assert_eq!(choose(5431, |p| p != 5431).unwrap(), 5440);
    }

    #[test]
    fn exhausted() {
        assert!(matches!(
            choose(49150, |_| false),
            Err(PortError::NoFreePort { start: 49150 })
        ));
    }

    #[test]
    fn probe_error_stops_the_scan_and_names_the_port() {
        let err = choose_port(DEFAULT_PORT, |p| {
            if p == 5419 {
                Err(io::Error::from(io::ErrorKind::PermissionDenied))
            } else {
                Ok(false)
            }
        })
        .unwrap_err();
        assert!(matches!(err, PortError::Probe { port: 5419, .. }), "{err}");
        assert!(err.to_string().contains("5419"), "{err}");
    }

    #[test]
    fn only_addr_in_use_is_taken() {
        assert!(is_taken(&io::Error::from(io::ErrorKind::AddrInUse)));
        assert!(!is_taken(&io::Error::from(io::ErrorKind::AddrNotAvailable)));
        assert_eq!(
            is_taken(&io::Error::from(io::ErrorKind::PermissionDenied)),
            cfg!(windows)
        );
    }

    #[test]
    fn wildcard_listener_is_taken() {
        let listener = TcpListener::bind("0.0.0.0:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(!port_is_free(port).unwrap());
    }

    #[test]
    fn real_bind() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        assert!(!port_is_free(port).unwrap());
    }
}
