#!/usr/bin/env nextflow

nextflow.enable.dsl=2

def python_bin = (params.python && params.python != 'null') ? params.python : "${projectDir}/.venv/bin/python"
params.source_json = params.source_json ?: 'data/raw/brenda_2025_1.json'
params.source_txt  = params.source_txt ?: 'data/raw/brenda_2025_1.txt'
params.db_path     = params.db_path ?: 'data/processed/brenda.db'
params.model       = params.model ?: 'gpt-oss:20b'
params.enable_chatbot = params.enable_chatbot ?: false
params.skip_ingest = params.skip_ingest ?: false

process ingest_brenda {
  tag "ingest"

  input:
    path source_json from file(params.source_json)
    path source_txt  from file(params.source_txt)

  output:
    path params.db_path

  script:
  """
  cd ${projectDir}
  ${python_bin} -m src.pipelines.brenda_ingestion \
      --source ${source_json} \
      --text ${source_txt} \
      --target ${params.db_path}
  """
}

process analysis_snapshot {
  tag "analysis"

  input:
    path db

  output:
    path "docs/brenda_analysis.md"

  script:
  """
  WORK_DIR=\$PWD
  cd ${projectDir}
  mkdir -p docs
  ${python_bin} -m src.pipelines.brenda_analysis --output docs/brenda_analysis.md
  mkdir -p "\$WORK_DIR/docs"
  cp docs/brenda_analysis.md "\$WORK_DIR/docs/brenda_analysis.md"
  """
}

process chatbot_demo {
  tag "chatbot"

  when:
    params.enable_chatbot

  input:
    path db

  output:
    path "artifacts/crew_demo.txt"

  script:
  """
  WORK_DIR=\$PWD
  cd ${projectDir}
  mkdir -p artifacts
  OUT_FILE=artifacts/crew_demo.txt MODEL_OVERRIDE='${params.model}' ${python_bin} - <<'PY'
import os
from src.crew import run_brenda_crew

model_override = os.environ.get('MODEL_OVERRIDE') or None
result = run_brenda_crew('Summarise inhibitors and kinetics for EC 2.1.1.247', model_override=model_override)
out_path = os.environ['OUT_FILE']
with open(out_path, 'w', encoding='utf-8') as fh:
    fh.write(result.final_answer)
    fh.write('''\n\n-- filter JSON --\n''')
    fh.write(str(result.filter_payload))
    fh.write('''\n\n-- query JSON --\n''')
    fh.write(str(result.query_payload))
PY
  mkdir -p "\$WORK_DIR/artifacts"
  cp artifacts/crew_demo.txt "\$WORK_DIR/artifacts/crew_demo.txt"
  """
}

workflow {
  Channel.fromPath(params.source_json)
  Channel.fromPath(params.source_txt)

  db_channel = params.skip_ingest
    ? Channel.fromPath(params.db_path)
    : ingest_brenda(Channel.fromPath(params.source_json), Channel.fromPath(params.source_txt))

  analysis_snapshot(db_channel)
  if (params.enable_chatbot) {
    chatbot_demo(db_channel)
  }
}
