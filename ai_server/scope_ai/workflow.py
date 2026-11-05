\
\
\
\
   
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
from typing import Callable

from .common import StoryPaths, load_json, save_json, validate_ep
from .analysis import analyze_submission
from .id_split import process_ep
from .embedding import embed_submission_events
from .ers import rank_related_events
from .review import review_submission
from .sources import extract_event_sources


def _paths(story_id: str, number: int, data_root=None):
    if number < 1:
        raise ValueError('submission_number must be positive')
    return StoryPaths(story_id, Path(data_root)) if data_root else StoryPaths(story_id)


def _state_path(paths, number):
    return paths.episodes_dir / f'ep{number}_workflow.json'


def _state(paths, number):
    path = _state_path(paths, number)
    if not path.exists():
        raise ValueError('No workflow state; call prepare_submission first')
    return load_json(path)


def prepare_submission(story_id: str, submission_number: int, submission_text: str, *, data_root=None, llm_callable=None):
    paths = _paths(story_id, submission_number, data_root)
    if _state_path(paths, submission_number).exists():
        raise ValueError('Submission already prepared; refusing to overwrite existing work')
    ep = analyze_submission(story_id, submission_number, submission_text, data_root=data_root, llm_callable=llm_callable)
    save_json({'status': 'draft', 'revision': 0, 'id_maps': None}, _state_path(paths, submission_number))
    return {'status': 'draft', 'analysis': ep}


def edit_submission(story_id: str, submission_number: int, edited_ep: dict, *, data_root=None):
    paths = _paths(story_id, submission_number, data_root)
    state = _state(paths, submission_number)
    if state['status'] not in ('draft', 'confirmed'):
        raise ValueError('Editing locked once secondary review starts')
    validate_ep(edited_ep)
    if state['status'] == 'confirmed':
        old_ep = load_json(paths.ep(submission_number))
        if old_ep == edited_ep:
            return {'status': 'confirmed', 'revision': state['revision'], 'changed': False}
        state['status'] = 'draft'
        state['previous_id_maps'] = deepcopy(state.get('id_maps') or {})
        state['previous_global_events'] = [
            deepcopy(event) for event in load_json(paths.ep_global)['events']
            if event.get('source_submission') == submission_number
        ]
        state['id_maps'] = None
    save_json(deepcopy(edited_ep), paths.ep(submission_number))
    state['revision'] += 1
    save_json(state, _state_path(paths, submission_number))
    return {'status': state['status'], 'revision': state['revision'], 'changed': True}


def confirm_submission(story_id: str, submission_number: int, *, data_root=None, embedder=None, top_k=None):
    paths = _paths(story_id, submission_number, data_root)
    state = _state(paths, submission_number)
    if state['status'] != 'draft':
        raise ValueError('Confirmation requires a draft; duplicate confirmation prohibited')
    ep = load_json(paths.ep(submission_number))
    validate_ep(ep)
    split = process_ep(story_id, submission_number, ep=ep, data_root=data_root, previous_id_maps=state.get("previous_id_maps"))
                                                                              
                                                                     
    extract_event_sources(story_id, submission_number, data_root=data_root, event_id_map=split["id_maps"].get("events"))
    state['status'] = 'processing'
    state['id_maps'] = split['id_maps']
    save_json(state, _state_path(paths, submission_number))
    return finish_confirmation(story_id, submission_number, data_root=data_root, embedder=embedder, top_k=top_k)


def finish_confirmation(story_id: str, submission_number: int, *, data_root=None, embedder=None, top_k=None):
    paths = _paths(story_id, submission_number, data_root)
    state = _state(paths, submission_number)
    if state['status'] != 'processing':
        raise ValueError('No confirmation processing to resume')
    embeddings = embed_submission_events(story_id, submission_number, data_root=data_root, embedder=embedder, previous_events=state.get("previous_global_events"))
    ers = rank_related_events(story_id, submission_number, data_root=data_root, top_k=top_k if top_k is not None else int(os.environ.get("ERS_TOP_K", "5")))
    affected = []
    if state.get('previous_global_events') is not None:
        for other in paths.ers_dir.glob('ers*.json'):
            if other != paths.ers_result(submission_number):
                other.unlink()
                affected.append(other.name)
    state['status'] = 'confirmed'
    state.pop('previous_id_maps', None)
    state.pop('previous_global_events', None)
    save_json(state, _state_path(paths, submission_number))
    return {'status': 'confirmed', 'embedding': embeddings, 'ers': ers, 'invalidated_ers': affected}


def _is_transient_api_error(error):
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    status_code = getattr(error, "status_code", None)
    if status_code in (408, 409, 429, 500, 502, 503, 504, 529):
        return True
    return type(error).__name__ in ("APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError")


def start_secondary_review(story_id: str, submission_number: int, *, data_root=None, llm_callable=None):
    paths = _paths(story_id, submission_number, data_root)
    state = _state(paths, submission_number)
    if state['status'] != 'confirmed':
        raise ValueError('Review requires confirmed data')
    state['status'] = 'reviewing'
    save_json(state, _state_path(paths, submission_number))
    try:
                                                                                       
        for attempt in range(2):
            try:
                result = review_submission(story_id, submission_number, data_root=data_root, llm_callable=llm_callable)
                if result.get('parse_error'):
                    raise ValueError('Review response is not valid JSON')
                state['status'] = 'reviewed'
                save_json(state, _state_path(paths, submission_number))
                return {'status': 'reviewed', 'review': result}
            except Exception as error:
                if attempt == 1 or not _is_transient_api_error(error):
                    raise
    except Exception:
        state['status'] = 'confirmed'
        save_json(state, _state_path(paths, submission_number))
        raise
