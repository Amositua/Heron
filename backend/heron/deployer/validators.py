from heron.models.build_plan import BuildPlan
from heron.models.deploy_result import ValidationCheck, ValidationReport
from heron.splunk.splunk_client import SplunkClient, SplunkClientError


def validate_deployment(client: SplunkClient, plan: BuildPlan) -> ValidationReport:
    checks: list[ValidationCheck] = [
        _check_app_installed(client, plan),
        _check_data_flowing(client, plan),
    ]
    checks.extend(_check_saved_searches(client, plan))
    checks.extend(_check_alerts(client, plan))

    return ValidationReport(passed=all(check.passed for check in checks), checks=checks)


def _check_app_installed(client: SplunkClient, plan: BuildPlan) -> ValidationCheck:
    installed = client.verify_app_installed(plan.app_name)
    return ValidationCheck(
        name="app_installed",
        passed=installed,
        detail=f"app '{plan.app_name}' {'is installed' if installed else 'is not installed'}",
    )


def _check_data_flowing(client: SplunkClient, plan: BuildPlan) -> ValidationCheck:
    sourcetype = plan.data_source.sourcetype
    flowing = client.verify_data_flowing(sourcetype, earliest_time="-5m")
    return ValidationCheck(
        name="data_flowing",
        passed=flowing,
        detail=(
            f"sourcetype={sourcetype}: "
            f"{'at least one event' if flowing else 'no events'} indexed in the last 5 minutes"
        ),
    )


def _check_saved_searches(client: SplunkClient, plan: BuildPlan) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for search in plan.saved_searches:
        ok = client.verify_search_returns(search.spl)
        checks.append(
            ValidationCheck(
                name=f"saved_search:{search.name}",
                passed=ok,
                detail=f"'{search.name}' {'ran without errors' if ok else 'failed to execute'}",
            )
        )
    return checks


def _check_alerts(client: SplunkClient, plan: BuildPlan) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for alert in plan.alerts:
        try:
            client.get_alert_firing_history(alert.search_name)
        except SplunkClientError:
            checks.append(
                ValidationCheck(
                    name=f"alert:{alert.name}",
                    passed=False,
                    detail=f"alert '{alert.name}' references unknown saved search '{alert.search_name}'",
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name=f"alert:{alert.name}",
                    passed=True,
                    detail=f"alert '{alert.name}' is registered on saved search '{alert.search_name}'",
                )
            )
    return checks
