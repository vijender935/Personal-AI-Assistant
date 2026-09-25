import {describe,expect,it} from "vitest";
import {parseSSEEvent} from "./sse";

describe("parseSSEEvent",()=>{
 it("parses typed JSON events",()=>{
  const received=[];
  parseSSEEvent('event: error\ndata: {"detail":"boom"}',(...args)=>received.push(args));
  expect(received).toEqual([["error",{detail:"boom"}]]);
 });

 it("defaults event type to delta",()=>{
  const received=[];
  parseSSEEvent('data: {"text":"hello"}',(type,data)=>received.push([type,data]));
  expect(received).toEqual([["delta",{text:"hello"}]]);
 });

 it("combines multiple data lines",()=>{
  const received=[];
  parseSSEEvent('event: message\ndata: {"text":"a",\ndata: "data":"b"}',(type,data)=>received.push([type,data]));
  expect(received).toEqual([["message",{text:"a","data":"b"}]]);
 });
});
