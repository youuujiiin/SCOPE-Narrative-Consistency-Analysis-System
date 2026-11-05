"""Calculate ERS for all ordered pairs of distinct events, using original Scope AI formulas."""
import argparse
import json
from pathlib import Path
from ers_core.features import (semantic_feature, action_feature, causal_feature,
    participant_feature, time_feature, location_feature)
from ers_core.calculator import calculate_ers


def read_json(path):
    with path.open('r',encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Calculate exhaustive ERS without self-pairs.')
    parser.add_argument('--story-dir', type=Path, default=Path(__file__).resolve().parent / 'story',
                        help='Input story folder (default: bundled story/ next to this script)')
    parser.add_argument('--output',type=Path,default=None,help='Output JSON path (default: story-dir/ers/ers_all_pairs.json)')
    args=parser.parse_args()
    story=args.story_dir.expanduser().resolve()
    if not (story/'ep_global.json').is_file() or not (story/'embeddings'/'event_embeddings.json').is_file():
        parser.error(
            f'입력 파일이 없습니다: {story}\n'
            f'필요한 파일:\n  {story / "ep_global.json"}\n'
            f'  {story / "embeddings" / "event_embeddings.json"}\n'
            'ZIP을 압축 해제한 뒤 run_all_pairs.py가 있는 폴더를 VS Code에서 열어 주세요.'
        )
    print(f'실행 스크립트: {Path(__file__).resolve()}')
    print(f'데이터 폴더: {story}')
    ep=read_json(story/'ep_global.json')
    embs=read_json(story/'embeddings'/'event_embeddings.json')
    events=ep['events']
    ids=[e['event_id'] for e in events]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate event IDs in ep_global.json')
    by_emb={e['event_id']:e for e in embs.get('events', [])}
    missing=sorted(set(ids)-set(by_emb))
    if missing:
        raise ValueError(f'Missing embeddings for {len(missing)} event(s): {missing[:10]}')
    by_time={e['time_id']:e for e in ep['times'] if e.get('time_id')}
    by_location={e['location_id']:e for e in ep['locations'] if e.get('location_id')}
    n=len(events)
    results={event_id:[] for event_id in ids}
    # Original formulas are symmetric. Calculate each unordered pair once,
    # save both A->B and B->A as independent records.
    for i,a in enumerate(events):
        for b in events[i+1:]:
            a_id,b_id=a['event_id'],b['event_id']
            aemb,bemb=by_emb[a_id],by_emb[b_id]
            score=calculate_ers(
                semantic=semantic_feature(aemb,bemb),
                action=action_feature(aemb,bemb),
                causal=causal_feature(aemb,bemb),
                participant=participant_feature(a,b),
                time=time_feature(by_time.get(a.get('time_id')),by_time.get(b.get('time_id'))),
                location=location_feature(by_location.get(a.get('location_id')),by_location.get(b.get('location_id'))),
            )
            results[a_id].append({'event_id':b_id,**score})
            results[b_id].append({'event_id':a_id,**score})
    output={
        'story_id':story.name,
        'event_count':n,
        'pair_count':n*(n-1),
        'self_comparisons_excluded':True,
        'formula':'Original Scope AI ERS (features.py / calculator.py / math_utils.py)',
        'events':[{'source_event_id':event_id,'comparisons':results[event_id]} for event_id in ids],
    }
    dest=args.output or story/'ers'/'ers_all_pairs.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('w',encoding='utf-8') as f:
        json.dump(output,f,ensure_ascii=False,indent=2)
    print(f'Events: {n}; directed comparisons: {n*(n-1)}; saved to: {dest}')

if __name__=='__main__':
    main()
