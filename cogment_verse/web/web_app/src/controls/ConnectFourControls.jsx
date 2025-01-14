// Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDocumentKeypressListener } from "../hooks/usePressedKeys";
import { WEB_ACTOR_NAME } from "../utils/constants";
import { Button } from "../components/Button";
import { KeyboardControlList } from "../components/KeyboardControlList";
import { CountdownCircleTimer } from "react-countdown-circle-timer";
import {
  serializePlayerAction,
  TEACHER_NOOP_ACTION,
  DType,
  deserializeObservationActionMask,
  Space,
} from "../utils/spaceSerialization";

const TURN_DURATION_SECS = 1;
const COLUMNS = [0, 1, 2, 3, 4, 5, 6];
const ACTION_SPACE = new Space({
  discrete: {
    n: COLUMNS.length,
  },
});
const ACTION_MASK_SPACE = new Space({
  box: {
    low: {
      // Only the dtype and shape of the lower bound are used to deserialize the observation
      dtype: DType.DTYPE_INT8,
      shape: [7],
    },
  },
});

export const ConnectFourEnvironments = [
  "environments.pettingzoo_adapter.ClassicEnvironment/pettingzoo.classic.connect_four_v3",
];
export const ConnectFourControls = ({ sendAction, observation, actorClass, ...props }) => {
  const currentPlayer = observation?.currentPlayer;
  const [turnKey, setTurnKey] = useState(0);
  useEffect(() => {
    setTurnKey((turnKey) => turnKey + 1);
    setExpectingAction(true);
  }, [currentPlayer]);

  const [expectingAction, setExpectingAction] = useState(true);

  const opponentStepDisabled = !expectingAction || currentPlayer === WEB_ACTOR_NAME;
  const opponentStep = useCallback(() => {
    if (!opponentStepDisabled) {
      sendAction(TEACHER_NOOP_ACTION);
      setExpectingAction(false);
    }
  }, [sendAction, opponentStepDisabled]);
  useDocumentKeypressListener(" ", opponentStep);

  const columns = useMemo(() => {
    const deserializedActionMask = deserializeObservationActionMask(ACTION_MASK_SPACE, observation);
    return COLUMNS.map((columnIndex) => ({
      disabled: !expectingAction || currentPlayer !== WEB_ACTOR_NAME || deserializedActionMask[columnIndex] !== 1,
      play: () => {
        sendAction(serializePlayerAction(ACTION_SPACE, columnIndex));
      },
    }));
  }, [expectingAction, currentPlayer, sendAction, observation]);

  return (
    <div {...props}>
      <div className="flex flex-row gap-4 mb-2 px-10">
        {COLUMNS.map((columnIndex) => (
          <Button
            key={columnIndex}
            className="flex-1 rounded-full aspect-square"
            onClick={columns[columnIndex].play}
            disabled={columns[columnIndex].disabled}
          >
            {`#${columnIndex + 1}`}
          </Button>
        ))}
      </div>
      <div className="flex flex-row gap-1">
        <Button
          className="flex-1 flex justify-center items-center gap-2"
          onClick={opponentStep}
          disabled={opponentStepDisabled}
        >
          <div className="flex-initial">
            <CountdownCircleTimer
              size={20}
              strokeWidth={5}
              strokeLinecap="square"
              key={turnKey}
              duration={TURN_DURATION_SECS}
              colors="#fff"
              trailColor="#555"
              isPlaying={!opponentStepDisabled}
              onComplete={opponentStep}
            />
          </div>
          <div className="flex-initial">Step to opponent turn</div>
        </Button>
      </div>
      <KeyboardControlList items={[["space", "step"]]} />
    </div>
  );
};
