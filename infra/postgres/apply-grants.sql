\set ON_ERROR_STOP on

-- Reset runtime grants first so rerunning this file removes privileges that a
-- previous release may have granted. Role names are configurable psql values.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"api_user", :"worker_user";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM :"api_user", :"worker_user";
REVOKE ALL ON SCHEMA public FROM :"api_user", :"worker_user";
GRANT USAGE ON SCHEMA public TO :"api_user", :"worker_user";

-- Browser-facing API: public catalog/status reads and the three vote tables.
GRANT SELECT ON TABLE
  source,
  source_record,
  observation,
  archive_product,
  gallery_item,
  item_asset,
  rendition,
  tag,
  item_tag,
  embedding,
  cluster,
  cluster_member,
  similarity_edge,
  collection,
  collection_item,
  active_vote,
  vote_total,
  ingest_run
TO :"api_user";
GRANT INSERT, DELETE ON TABLE active_vote TO :"api_user";
GRANT INSERT ON TABLE vote_event TO :"api_user";
GRANT INSERT ON TABLE vote_total TO :"api_user";
GRANT UPDATE (count) ON TABLE vote_total TO :"api_user";

-- Worker: trusted input resolution, SKIP LOCKED leasing, render/embed chaining,
-- stable cluster graph replacement, and append-or-refresh link-check results.
GRANT SELECT ON TABLE
  source_record,
  archive_product,
  gallery_item,
  item_asset,
  rendition,
  embedding,
  cluster,
  cluster_member,
  link_check,
  ingest_run,
  jobs
TO :"worker_user";
GRANT INSERT ON TABLE
  rendition,
  embedding,
  cluster,
  cluster_member,
  similarity_edge,
  link_check,
  jobs
TO :"worker_user";
GRANT UPDATE (
  width,
  height,
  recipe,
  alt_text,
  credit,
  rights,
  rights_url,
  last_verified_at,
  updated_at
) ON TABLE rendition TO :"worker_user";
GRANT UPDATE (vector, perceptual_hash, updated_at)
  ON TABLE embedding TO :"worker_user";
GRANT UPDATE (editorial_state, metadata_json, processing_note, updated_at)
  ON TABLE gallery_item TO :"worker_user";
GRANT UPDATE (
  content_class,
  algorithm_version,
  representative_item_id,
  centroid,
  archived_at,
  updated_at
) ON TABLE cluster TO :"worker_user";
GRANT DELETE ON TABLE cluster_member, similarity_edge TO :"worker_user";
GRANT UPDATE (ok, status_code, final_url, error, checked_at)
  ON TABLE link_check TO :"worker_user";
GRANT UPDATE (
  status,
  attempts,
  available_at,
  locked_by,
  locked_at,
  result_json,
  error,
  updated_at
) ON TABLE jobs TO :"worker_user";
