import {describe,expect,it} from "vitest";
import {getEditableLastUser,responseDetailFromPayload} from "./useChat";

describe("getEditableLastUser",()=>{
 it("returns the final user message when followed by an assistant",()=>{
  expect(getEditableLastUser([
   {role:"user",content:"first"},
   {role:"assistant",content:"answer"},
   {role:"user",content:"edit me"},
   {role:"assistant",content:"reply"}
  ])).toEqual({value:"edit me",index:2});
 });
 it("returns null when the last message is not an assistant reply",()=>{
  expect(getEditableLastUser([{role:"user",content:"only"}])).toBeNull();
 });
 it("returns null for missing or too-short history",()=>{
  expect(getEditableLastUser()).toBeNull();
  expect(getEditableLastUser([])).toBeNull();
 });
});

describe("responseDetailFromPayload",()=>{
 it("prefers a backend detail",()=>{
  expect(responseDetailFromPayload({detail:"Unauthorized"},"Fallback")).toBe("Unauthorized");
 });
 it("falls back when detail is missing",()=>{
  expect(responseDetailFromPayload({},"Fallback")).toBe("Fallback");
 });
});
