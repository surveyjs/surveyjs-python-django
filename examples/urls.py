"""Every path of the integration, once, in the order of the integration docs. by_method() picks the view per HTTP
method where two examples share a path. The relays' WebSocket routes are in examples/routing.py.

The switches choose a view when this module is imported (restart the app after changing settings.env):
VALIDATE_RESPONSES routes POST /api/responses to validate_response.py, and LINT_DEFINITIONS routes
PUT /api/forms/<id> to lint_definition.py.
"""

from django.conf import settings
from django.urls import path

from examples.routing import by_method
from examples.views import (
    ai_translation,
    async_functions,
    choices_from_web,
    creator_load_save,
    dashboard,
    extract_from_paper,
    lint_definition,
    load_definition_variables_data,
    relational_storage,
    resume_progress,
    save_response,
    server_pdf,
    store_files,
    validate_response,
    variable_presets,
)

save = validate_response.save if settings.VALIDATE_RESPONSES else save_response.save
put_form = lint_definition.put_form if settings.LINT_DEFINITIONS else creator_load_save.put_form

urlpatterns = [
    # Run Forms
    path("api/responses", by_method(POST=save, GET=dashboard.responses)),   # save-response, dashboard
    path("claim", by_method(GET=load_definition_variables_data.claim_page)),   # Option A
    path("api/forms/<str:form_id>", by_method(GET=load_definition_variables_data.get_form, PUT=put_form)),   # Option B, creator-load-save
    path("api/progress/<str:form_id>", by_method(GET=resume_progress.load_progress, PUT=resume_progress.save_progress,
                                                 DELETE=resume_progress.delete_progress)),
    path("api/files", by_method(POST=store_files.upload)),
    path("api/files/<str:file_id>", by_method(GET=store_files.download)),
    path("api/offices", by_method(GET=choices_from_web.offices)),
    path("api/countries", by_method(GET=choices_from_web.countries)),
    path("api/customers/exists", by_method(GET=async_functions.customer_exists)),
    path("api/shipping", by_method(GET=async_functions.shipping)),
    path("api/claims", by_method(POST=relational_storage.save_claim)),
    # fill-together: WebSocket /ws/rooms/<record_id> (examples/routing.py)

    # Analyze Results with Dashboard: GET /api/responses, above

    # Edit Forms in Survey Creator (creator-uploads reuses POST /api/files and PUT /api/forms/<id>)
    path("api/translate", by_method(POST=ai_translation.translate)),
    path("api/variable-presets/<str:form_id>", by_method(GET=variable_presets.load_presets, PUT=variable_presets.save_presets)),
    # edit-together: WebSocket /ws/forms/<form_id> (examples/routing.py)

    # Run Server-Side Workflows (validate-response and lint-definition are switched in above)
    path("api/claims/<int:claim_id>/pdf", by_method(GET=server_pdf.claim_pdf)),
    path("api/work-orders/blank.pdf", by_method(GET=extract_from_paper.blank_work_order)),
    path("api/work-orders/extract", by_method(POST=extract_from_paper.extract_work_order)),
]
