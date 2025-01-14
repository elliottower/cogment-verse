# Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import logging
import sys
from multiprocessing import Process, Queue
from typing import Awaitable, Callable

import cogment
from cogment.datastore import Datastore, DatastoreSample
from cogment.model_registry_v2 import ModelRegistry

from cogment_verse.services_directory import ServiceDirectory

log = logging.getLogger(__name__)


class SampleQueueEvent:
    def __init__(self, trial_id=None, trial_idx=None, sample=None, done=False):
        self.trial_id = trial_id
        self.trial_idx = trial_idx
        self.sample = sample
        self.done = done


class SampleProducerSession:
    def __init__(
        self,
        datastore: Datastore,
        trial_idx: int,
        trial_info: list,
        sample_queue: Queue,
        model_registry: ModelRegistry,
        impl: Callable[["SampleProducerSession"], Awaitable],
    ):
        self.trial_idx = trial_idx
        self.datastore = datastore
        self.trial_info = trial_info
        self.sample_queue = sample_queue
        self.model_registry = model_registry
        self.impl = impl

    def produce_sample(self, sample):
        self.sample_queue.put(
            SampleQueueEvent(trial_id=self.trial_info.trial_id, trial_idx=self.trial_idx, sample=sample)
        )

    def all_trial_samples(self) -> DatastoreSample:
        return self.datastore.all_samples([self.trial_info])

    def create_task(self):
        async def wrapped_impl():
            try:
                await self.impl(self)
            except KeyboardInterrupt:
                # This one is ignored, it's logged at a bunch of different places
                pass
            except Exception as error:
                log.error(
                    f"Uncaught error occured during the sample production for trial [{self.trial_info.trial_id}]",
                    exc_info=error,
                )
                raise

        return asyncio.create_task(wrapped_impl())


async def async_sample_producer_worker(trial_started_queue, sample_queue, impl, services_directory: ServiceDirectory):
    # Importing 'specs' only in the subprocess (i.e. where generate has been properly executed)
    # pylint: disable-next=import-outside-toplevel
    from cogment_verse.specs import cog_settings

    context = cogment.Context(cog_settings=cog_settings, user_id="cogment_verse_sample_producer")
    datastore = await services_directory.get_datastore(context)
    model_registry = await services_directory.get_model_registry(context)

    # Define a timeout for trial info retrieval
    # pylint: disable-next=protected-access
    datastore._timeout = 60

    sample_producer_tasks = []
    while True:
        # Executing the retrieval from the queue as an async corouting to avoid blocking the process
        trial_started_queue_event = await asyncio.get_running_loop().run_in_executor(None, trial_started_queue.get)
        if trial_started_queue_event.done:
            break

        trials_info = await datastore.get_trials([trial_started_queue_event.trial_id])
        if len(trials_info) == 0:
            log.warning(
                f"Trial [{trial_started_queue_event.trial_id}] couldn't be found in the trial datastore, retrying later"
            )
            await asyncio.get_running_loop().run_in_executor(None, trial_started_queue.put, trial_started_queue_event)
            continue

        [trial_info] = trials_info

        log.debug(f"[{trial_info.trial_id}] started")

        sample_producer_session = SampleProducerSession(
            datastore=datastore,
            trial_idx=trial_started_queue_event.trial_idx,
            trial_info=trial_info,
            sample_queue=sample_queue,
            model_registry=model_registry,
            impl=impl,
        )

        sample_producer_tasks.append(sample_producer_session.create_task())

    if len(sample_producer_tasks) > 0:
        await asyncio.wait(sample_producer_tasks)

    sample_queue.put(SampleQueueEvent(done=True))


def sample_producer_worker(trial_started_queue, sample_queue, impl, services_directory: ServiceDirectory):
    try:
        asyncio.run(async_sample_producer_worker(trial_started_queue, sample_queue, impl, services_directory))
    except Exception as error:
        log.error("Uncaught error occured during the sample production for trial", exc_info=error)
        raise
    except KeyboardInterrupt:
        sys.exit(-1)


def start_sample_producer_worker(trial_started_queue, sample_queue, impl, services_directory: ServiceDirectory):
    worker = Process(
        name="sample_producer_worker",
        target=sample_producer_worker,
        args=(
            trial_started_queue,
            sample_queue,
            impl,
            services_directory,
        ),
    )
    worker.start()
    return worker
