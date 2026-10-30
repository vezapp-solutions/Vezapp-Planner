import { describe, expect, it } from "vitest";

import { allowedMachines, dayCell, hours, machineOn, nextStep, opTitle, runsOn, setTypeTime, timedTypes, toggleMachine, toggleType } from "./machining";

const VMC = 1;
const HMC = 2;
const CNC = 3;
const machines = [
  { id: 11, code: "VMC-1", resource_type: VMC },
  { id: 12, code: "VMC-2", resource_type: VMC },
  { id: 14, code: "HMC-1", resource_type: HMC },
  { id: 13, code: "CNC-1", resource_type: CNC },
];
const step = (over = {}) => ({ machine_types: [] as number[], except_ids: [] as number[], resource_ids: [] as number[], time_by_type: {} as Record<string, number>, ...over });

describe("opTitle", () => {
  it("joins the name, the OP number and the label", () => {
    expect(opTitle({ name: "Machining", step: 10, label: "Rough milling" })).toBe("Machining OP10 Rough milling");
    expect(opTitle({ name: "Machining", step: 0, label: "" })).toBe("Machining");
    expect(opTitle({ name: "Machining", step: 20, label: "" })).toBe("Machining OP20");
  });
});

describe("which machines may run a step", () => {
  it("takes every machine of an allowed type", () => {
    expect(allowedMachines(step({ machine_types: [VMC, HMC] }), machines).map((m) => m.code)).toEqual(["VMC-1", "VMC-2", "HMC-1"]);
  });
  it("leaves out machines marked unsuitable", () => {
    expect(allowedMachines(step({ machine_types: [VMC], except_ids: [12] }), machines).map((m) => m.code)).toEqual(["VMC-1"]);
  });
  it("adds machines chosen one by one, even of another type", () => {
    expect(allowedMachines(step({ machine_types: [VMC], resource_ids: [13] }), machines).map((m) => m.code)).toEqual(["VMC-1", "VMC-2", "CNC-1"]);
  });
  it("allows nothing by default", () => expect(allowedMachines(step(), machines)).toEqual([]));
  it("an unsuitable machine chosen on its own is still allowed", () => expect(machineOn(step({ machine_types: [VMC], except_ids: [11], resource_ids: [11] }), machines[0])).toBe(true));
});

describe("toggleMachine", () => {
  it("unticking a machine of an allowed type marks it unsuitable", () => {
    expect(toggleMachine(step({ machine_types: [VMC] }), machines[1])).toEqual({ resource_ids: [], except_ids: [12] });
  });
  it("ticking it again clears the mark", () => {
    expect(toggleMachine(step({ machine_types: [VMC], except_ids: [12] }), machines[1])).toEqual({ resource_ids: [], except_ids: [] });
  });
  it("ticking a machine of a type that is not allowed chooses it on its own", () => {
    expect(toggleMachine(step({ machine_types: [VMC] }), machines[3])).toEqual({ resource_ids: [13], except_ids: [] });
  });
  it("unticking a machine chosen on its own drops it", () => {
    expect(toggleMachine(step({ resource_ids: [13] }), machines[3])).toEqual({ resource_ids: [], except_ids: [] });
  });
});

describe("toggleType", () => {
  it("allows a type", () => expect(toggleType(step(), VMC, machines).machine_types).toEqual([VMC]));
  it("leaving a type forgets its time and its exceptions only", () => {
    const next = toggleType(step({ machine_types: [VMC, HMC], except_ids: [12, 14], time_by_type: { "1": 12, "2": 7 } }), VMC, machines);
    expect(next).toEqual({ machine_types: [HMC], except_ids: [14], time_by_type: { "2": 7 } });
  });
});

describe("times by type", () => {
  it("sets and clears one type's time without touching the others", () => {
    const t = setTypeTime({ "1": 12 }, HMC, 7);
    expect(t).toEqual({ "1": 12, "2": 7 });
    expect(setTypeTime(t, VMC, null)).toEqual({ "2": 7 });
  });
  it("lists the types that need a time", () => {
    expect(timedTypes(step({ machine_types: [VMC], resource_ids: [13] }), machines).sort()).toEqual([VMC, CNC]);
  });
});

describe("nextStep", () => {
  it("proposes 10, then the next multiple of ten", () => {
    expect(nextStep([{ type_code: "machining", step: 0 }], "machining")).toBe(10);
    expect(nextStep([{ type_code: "machining", step: 10 }, { type_code: "machining", step: 20 }], "machining")).toBe(30);
    expect(nextStep([{ type_code: "machining", step: 15 }], "machining")).toBe(20);
    expect(nextStep([{ type_code: "fettling", step: 0 }], "machining")).toBe(10);
  });
});

describe("hours and day cells", () => {
  it("writes minutes as hours", () => {
    expect(hours(382.5)).toBe("6.4");
    expect(hours(0)).toBe("0.0");
  });
  it("prints the share used and the free hours", () => {
    expect(dayCell({ capacity: 765, load: 382.5, free: 382.5, utilisation: 0.5 })).toEqual({ main: "50%", sub: "6.4 h free", title: "6.4 of 12.8 hours used", off: false });
  });
  it("says off when a machine has no working time that day", () => {
    expect(dayCell({ capacity: 0, load: 0, free: 0, utilisation: null }).main).toBe("off");
    expect(dayCell(undefined).off).toBe(true);
  });
});

describe("runsOn", () => {
  it("names the machines in plain words", () => {
    expect(runsOn(step({ machine_types: [VMC, HMC] }), machines)).toBe("Runs on VMC-1, VMC-2 and HMC-1.");
    expect(runsOn(step({ machine_types: [HMC] }), machines)).toBe("Runs on HMC-1.");
  });
  it("says so when no machine is allowed", () => expect(runsOn(step(), machines)).toContain("No machine is allowed yet"));
});
