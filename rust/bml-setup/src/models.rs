//! The approved language models and what it takes to have them.

/// A model BMLibrarian expects Ollama to have.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ApprovedModel {
    /// The name the applications ask Ollama for.
    pub name: &'static str,
    /// The name to pull from the registry (copied to `name` if different).
    pub pull_as: &'static str,
    /// Rough download size in bytes, for disk checks.
    pub approx_bytes: u64,
}

/// The models setup guarantees, exactly.
pub const APPROVED_MODELS: [ApprovedModel; 2] = [
    ApprovedModel {
        name: "gpt-oss:20b",
        pull_as: "gpt-oss:20b",
        approx_bytes: 13_800_000_000,
    },
    ApprovedModel {
        name: "medgemma4B_it_q8:latest",
        pull_as: "medgemma1.5:4b-it-q8_0",
        approx_bytes: 5_000_000_000,
    },
];

/// What is needed to have a model.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelAction {
    /// Already installed.
    Present,
    /// The pulled name is installed; copy it to the approved name.
    Copy,
    /// Pull, then copy to the approved name.
    PullThenCopy,
    /// Pull (the names are equal).
    Pull,
}

/// Decide what to do for `model` given the installed model names.
#[must_use]
pub fn model_action(model: &ApprovedModel, installed: &[String]) -> ModelAction {
    let has = |n: &str| installed.iter().any(|i| crate::ollama::same_model(i, n));
    if has(model.name) {
        ModelAction::Present
    } else if model.pull_as != model.name {
        if has(model.pull_as) {
            ModelAction::Copy
        } else {
            ModelAction::PullThenCopy
        }
    } else {
        ModelAction::Pull
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s(v: &[&str]) -> Vec<String> {
        v.iter().map(|x| x.to_string()).collect()
    }

    #[test]
    fn model_action_table() {
        let [gpt, med] = &APPROVED_MODELS;
        assert_eq!(
            model_action(gpt, &s(&["gpt-oss:20b"])),
            ModelAction::Present
        );
        assert_eq!(model_action(gpt, &[]), ModelAction::Pull);
        assert_eq!(
            model_action(med, &s(&["medgemma4B_it_q8:latest"])),
            ModelAction::Present
        );
        assert_eq!(
            model_action(med, &s(&["medgemma1.5:4b-it-q8_0"])),
            ModelAction::Copy
        );
        assert_eq!(
            model_action(med, &s(&["gpt-oss:20b"])),
            ModelAction::PullThenCopy
        );
    }
}
