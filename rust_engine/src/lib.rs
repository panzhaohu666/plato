use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};

// ============================================================
// Data Structures
// ============================================================

/// Represents one column's formula. If `dependencies` is empty,
/// the column is a leaf (source data, no computation needed).
#[derive(Debug, Deserialize)]
struct ColumnDef {
    name: String,
    #[serde(default)]
    dependencies: Vec<String>,
}

/// Input from Django: a list of column definitions with their dependencies.
#[derive(Debug, Deserialize)]
struct DependencyInput {
    columns: Vec<ColumnDef>,
}

/// A single computation group: columns that can be computed in parallel.
#[derive(Debug, Serialize)]
struct ComputationGroup {
    level: usize,
    columns: Vec<String>,
}

/// Output to Django: sorted computation plan.
#[derive(Debug, Serialize)]
struct ComputationPlan {
    /// Ordered groups — all columns in group[i] depend only on groups[0..i-1]
    order: Vec<Vec<String>>,
    has_cycle: bool,
    cycles: Vec<Vec<String>>,
}

// ============================================================
// Core Algorithm: Kahn's Topological Sort with Level Grouping
// ============================================================

fn compute_plan(input: &DependencyInput) -> ComputationPlan {
    let mut in_degree: HashMap<&str, usize> = HashMap::new();
    let mut adj: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut all_nodes: HashSet<&str> = HashSet::new();

    // Build graph
    for col in &input.columns {
        all_nodes.insert(&col.name);
        in_degree.entry(&col.name).or_insert(0);

        for dep in &col.dependencies {
            all_nodes.insert(dep.as_str());
            adj.entry(dep.as_str())
                .or_default()
                .push(&col.name);
            *in_degree.entry(&col.name).or_insert(0) += 1;
        }
    }

    // Ensure all nodes are in in_degree map
    for node in &all_nodes {
        in_degree.entry(node).or_insert(0);
        adj.entry(node).or_default();
    }

    // Kahn's algorithm: queue nodes with in_degree == 0
    let mut queue: VecDeque<&str> = VecDeque::new();
    let mut level: HashMap<&str, usize> = HashMap::new();

    for (&node, &deg) in &in_degree {
        if deg == 0 {
            queue.push_back(node);
            level.insert(node, 0);
        }
    }

    let mut sorted: Vec<&str> = Vec::new();

    while let Some(node) = queue.pop_front() {
        sorted.push(node);
        let current_level = *level.get(node).unwrap_or(&0);

        if let Some(neighbors) = adj.get(node) {
            for &neighbor in neighbors {
                if let Some(deg) = in_degree.get_mut(neighbor) {
                    *deg -= 1;
                    if *deg == 0 {
                        queue.push_back(neighbor);
                        level.insert(neighbor, current_level + 1);
                    }
                }
            }
        }
    }

    // Cycle detection
    let has_cycle = sorted.len() != all_nodes.len();

    // Build cycle information if present
    let cycles: Vec<Vec<String>> = if has_cycle {
        find_cycles(&adj, &in_degree, &all_nodes, &sorted)
    } else {
        Vec::new()
    };

    // Group by level for parallel computation
    let max_level = level.values().max().copied().unwrap_or(0);
    let mut order: Vec<Vec<String>> = vec![Vec::new(); max_level + 1];

    for node in &sorted {
        let lvl = *level.get(node).unwrap_or(&0);
        order[lvl].push(node.to_string());
    }

    // Remove empty groups
    order.retain(|g| !g.is_empty());

    ComputationPlan {
        order,
        has_cycle,
        cycles,
    }
}

/// Find actual cycles in the remaining graph (nodes with in_degree > 0).
fn find_cycles(
    adj: &HashMap<&str, Vec<&str>>,
    _in_degree: &HashMap<&str, usize>,
    all_nodes: &HashSet<&str>,
    sorted: &[&str],
) -> Vec<Vec<String>> {
    let sorted_set: HashSet<&str> = sorted.iter().copied().collect();
    let remaining: HashSet<&str> = all_nodes
        .iter()
        .filter(|n| !sorted_set.contains(*n))
        .copied()
        .collect();

    let mut cycles: Vec<Vec<String>> = Vec::new();
    let mut visited: HashSet<&str> = HashSet::new();

    for &start in &remaining {
        if visited.contains(start) {
            continue;
        }

        // DFS to find a cycle
        let mut stack: Vec<&str> = Vec::new();
        let mut path: Vec<&str> = Vec::new();
        let mut in_path: HashSet<&str> = HashSet::new();

        stack.push(start);

        while let Some(node) = stack.pop() {
            if in_path.contains(node) {
                // Found a cycle — extract it from path
                if let Some(pos) = path.iter().position(|&n| n == node) {
                    let cycle: Vec<String> = path[pos..]
                        .iter()
                        .map(|s| s.to_string())
                        .collect();
                    if !cycle.is_empty() {
                        cycles.push(cycle);
                    }
                }
                continue;
            }

            if visited.contains(node) {
                continue;
            }

            visited.insert(node);
            in_path.insert(node);
            path.push(node);

            if let Some(neighbors) = adj.get(node) {
                for &neighbor in neighbors {
                    if remaining.contains(neighbor) {
                        stack.push(neighbor);
                    }
                }
            }
        }
    }

    cycles
}

// ============================================================
// PyO3 Bindings
// ============================================================

/// A Python module for high-performance dependency graph analysis.
///
/// Provides topological sort, cycle detection, and optimal batch
/// computation order for dynamic table column formulas.
#[pymodule]
fn rust_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(resolve_dependencies, m)?)?;
    m.add_function(wrap_pyfunction!(detect_cycles, m)?)?;
    Ok(())
}

/// Resolve column dependencies and return the optimal computation order.
///
/// Args:
///     columns_json: JSON string describing column names and their dependencies.
///         Format: [{"name": "col_a", "dependencies": ["col_b", "col_c"]}, ...]
///         Columns with no dependencies should omit the field or use [].
///
/// Returns:
///     JSON string with:
///         order: [[group0_columns], [group1_columns], ...]
///             Each group can be computed in parallel.
///             Group N depends only on groups 0..N-1.
///         has_cycle: true if circular dependencies were found
///         cycles: list of detected cycles (empty if has_cycle is false)
///
/// Raises:
///     ValueError: if the input JSON is malformed
///
/// Example:
///     >>> rust_engine.resolve_dependencies('[{"name":"total","dependencies":["a","b"]},{"name":"a"},{"name":"b"}]')
///     '{"order":[["a","b"],["total"]],"has_cycle":false,"cycles":[]}'
#[pyfunction]
fn resolve_dependencies(columns_json: &str) -> PyResult<String> {
    // Parse input JSON — accepts either array or {"columns": [...]} format
    let columns: Vec<ColumnDef> = serde_json::from_str(columns_json)
        .or_else(|_| {
            // Try wrapped format
            let wrapped: DependencyInput = serde_json::from_str(columns_json)?;
            Ok(wrapped.columns)
        })
        .map_err(|e: serde_json::Error| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "Invalid JSON: {}. Expected array of [{{'name': 'col', 'dependencies': [...]}}, ...]",
                e
            ))
        })?;

    let input = DependencyInput { columns };

    // Compute the plan (GIL already held in pyfunction context)
    let plan = compute_plan(&input);

    // Serialize output
    let output = serde_json::to_string(&plan).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("Serialization error: {}", e))
    })?;

    Ok(output)
}

/// Quick check: do these columns have circular dependencies?
///
/// Args:
///     columns_json: Same format as resolve_dependencies.
///
/// Returns:
///     JSON string: {"has_cycle": bool, "cycles": [...]}
#[pyfunction]
fn detect_cycles(columns_json: &str) -> PyResult<String> {
    let columns: Vec<ColumnDef> = serde_json::from_str(columns_json)
        .or_else(|_| {
            let wrapped: DependencyInput = serde_json::from_str(columns_json)?;
            Ok(wrapped.columns)
        })
        .map_err(|e: serde_json::Error| {
            pyo3::exceptions::PyValueError::new_err(format!("Invalid JSON: {}", e))
        })?;

    let input = DependencyInput { columns };
    let plan = compute_plan(&input);

    let result = serde_json::json!({
        "has_cycle": plan.has_cycle,
        "cycles": plan.cycles,
    });

    Ok(result.to_string())
}


// ============================================================
// Tests
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_chain() {
        let input = DependencyInput {
            columns: vec![
                ColumnDef { name: "c".into(), dependencies: vec!["b".into()] },
                ColumnDef { name: "b".into(), dependencies: vec!["a".into()] },
                ColumnDef { name: "a".into(), dependencies: vec![] },
            ],
        };
        let plan = compute_plan(&input);
        assert!(!plan.has_cycle);
        assert_eq!(plan.order.len(), 3);
        assert_eq!(plan.order[0], vec!["a"]);
        assert_eq!(plan.order[1], vec!["b"]);
        assert_eq!(plan.order[2], vec!["c"]);
    }

    #[test]
    fn test_parallel_groups() {
        let input = DependencyInput {
            columns: vec![
                ColumnDef { name: "total".into(), dependencies: vec!["a".into(), "b".into()] },
                ColumnDef { name: "a".into(), dependencies: vec![] },
                ColumnDef { name: "b".into(), dependencies: vec![] },
                ColumnDef { name: "c".into(), dependencies: vec![] },
            ],
        };
        let plan = compute_plan(&input);
        assert!(!plan.has_cycle);
        assert_eq!(plan.order.len(), 2);
        // Level 0 should contain all 3 source columns
        assert_eq!(plan.order[0].len(), 3);
        assert!(plan.order[0].contains(&"a".to_string()));
        assert!(plan.order[0].contains(&"b".to_string()));
        assert!(plan.order[0].contains(&"c".to_string()));
        assert_eq!(plan.order[1], vec!["total"]);
    }

    #[test]
    fn test_cycle_detection() {
        let input = DependencyInput {
            columns: vec![
                ColumnDef { name: "a".into(), dependencies: vec!["b".into()] },
                ColumnDef { name: "b".into(), dependencies: vec!["c".into()] },
                ColumnDef { name: "c".into(), dependencies: vec!["a".into()] },
            ],
        };
        let plan = compute_plan(&input);
        assert!(plan.has_cycle);
        assert!(!plan.cycles.is_empty());
    }

    #[test]
    fn test_self_loop() {
        let input = DependencyInput {
            columns: vec![
                ColumnDef { name: "a".into(), dependencies: vec!["a".into()] },
            ],
        };
        let plan = compute_plan(&input);
        assert!(plan.has_cycle);
    }

    #[test]
    fn test_no_dependencies() {
        let input = DependencyInput {
            columns: vec![
                ColumnDef { name: "x".into(), dependencies: vec![] },
                ColumnDef { name: "y".into(), dependencies: vec![] },
            ],
        };
        let plan = compute_plan(&input);
        assert!(!plan.has_cycle);
        assert_eq!(plan.order.len(), 1);
        assert_eq!(plan.order[0].len(), 2);
    }
}
