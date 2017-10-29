from scannerpy import Database, DeviceType, BulkJob, Job
from scannerpy.stdlib import parsers
import numpy as np
import cv2
import os.path
import util

with Database(master='localhost:8080', start_cluster=False) as db:
    print 'Connected!'

    example_video_path = 'tvnews/segments/FOXNEWS_20121009_220000_Special_Report_With_Bret_Baier_segment.mp4'

    [input_table], failed = db.ingest_videos([('example2', example_video_path)], force=True)

    frame = db.ops.FrameInput()
    hist = db.ops.Histogram(frame=frame)
    output_op = db.ops.Output(columns=[hist])

    job = Job(
        op_args={
            frame: db.table('example2').column('frame'),
            output_op: '_ignore'
        }
    )
    bulk_job = BulkJob(output=output_op, jobs=[job])

    output = db.run(bulk_job, force=True)
