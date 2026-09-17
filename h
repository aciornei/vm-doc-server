SELECT
    id,
    prometheus_source_id,
    instance_value,
    target_url,
    matched_vm_id,
    match_method,
    match_value,
    match_confidence
FROM monitoring_targets
WHERE instance_value = 'ns2.xxx.ro:9100'
   OR target_url = 'ns2.xxx.ro:9100';
